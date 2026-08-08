#!/usr/bin/env python3
"""
template_renderer.py - 模板变量替换工具

功能：
  - 读取文本模板，替换 {{var}} 占位符
  - 变量来源：命令行 JSON、JSON 配置文件、环境变量
  - 支持嵌套变量 {{user.name}} 与默认值 {{name|default:"Anonymous"}}
  - 批量渲染：从 CSV/JSON 读取多行数据，批量生成文档

依赖：jinja2
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

try:
    from jinja2 import (
        BaseLoader,
        ChainableUndefined,
        Environment,
        StrictUndefined,
    )
except ImportError:
    print("错误: 未安装 jinja2，请执行: pip install jinja2", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# 默认值语法兼容：{{name|default:"Anonymous"}} / {{name|default:'Anonymous'}}
# 转换为 Jinja2 标准：{{ name|default("Anonymous") }}
# ---------------------------------------------------------------------------
_DEFAULT_COLON_RE = re.compile(
    r"\{\{\s*([^{}|]+?)\s*\|\s*default\s*:\s*(['\"])(.*?)\2\s*\}\}"
)


def normalize_default_syntax(template_text: str) -> str:
    """将 {{var|default:"x"}} 转为 Jinja2 的 {{ var|default("x") }}。"""

    def _repl(m: re.Match) -> str:
        var = m.group(1).strip()
        quote = m.group(2)
        value = m.group(3)
        return f"{{{{ {var}|default({quote}{value}{quote}) }}}}"

    return _DEFAULT_COLON_RE.sub(_repl, template_text)


def make_env(strict: bool = False) -> Environment:
    """创建 Jinja2 环境。strict=True 时未定义变量会报错。"""
    # ChainableUndefined 允许 {{ user.name|default("N/A") }} 在 user 缺失时仍可链式取值
    undefined = StrictUndefined if strict else ChainableUndefined
    return Environment(
        loader=BaseLoader(),
        undefined=undefined,
        autoescape=False,
        keep_trailing_newline=True,
    )


def flatten_env_vars(prefix: str | None = None) -> dict[str, Any]:
    """
    从环境变量构建上下文。
    - 无前缀：全部环境变量（字符串值）
    - 有前缀：仅匹配前缀；去掉前缀后作为键；双下划线转为嵌套。
    """
    result: dict[str, Any] = {}
    for key, value in os.environ.items():
        if prefix:
            if not key.startswith(prefix):
                continue
            key = key[len(prefix) :]
        if "__" in key:
            parts = key.split("__")
            if prefix:
                parts = [p.lower() for p in parts]
            node: dict[str, Any] = result
            for p in parts[:-1]:
                nxt = node.get(p)
                if not isinstance(nxt, dict):
                    nxt = {}
                    node[p] = nxt
                node = nxt
            node[parts[-1]] = value
        else:
            result[key if not prefix else key.lower()] = value
    return result


def load_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"JSON 变量文件必须是对象(object): {path}")
    return data


def parse_vars_json(text: str) -> dict[str, Any]:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("--vars 必须是 JSON 对象，例如 '{\"name\": \"Alice\"}'")
    return data


def merge_contexts(*contexts: dict[str, Any]) -> dict[str, Any]:
    """递归合并字典，后面的覆盖前面的。"""
    merged: dict[str, Any] = {}

    def _merge(base: dict, overlay: dict) -> dict:
        out = dict(base)
        for k, v in overlay.items():
            if k in out and isinstance(out[k], dict) and isinstance(v, dict):
                out[k] = _merge(out[k], v)
            else:
                out[k] = v
        return out

    for ctx in contexts:
        if ctx:
            merged = _merge(merged, ctx)
    return merged


def render_template(
    template_text: str,
    context: dict[str, Any],
    strict: bool = False,
) -> str:
    text = normalize_default_syntax(template_text)
    env = make_env(strict=strict)
    tmpl = env.from_string(text)
    return tmpl.render(**context)


def load_batch_rows(path: Path) -> list[dict[str, Any]]:
    """从 CSV 或 JSON 加载批量数据行。"""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = [dict(row) for row in reader]
        if not rows:
            raise ValueError(f"CSV 无数据行: {path}")
        return rows
    if suffix == ".json":
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict) and isinstance(data.get("items"), list):
            rows = data["items"]
        else:
            raise ValueError("批量 JSON 必须是对象数组，或含 items 数组的对象")
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"批量 JSON 第 {i} 项不是对象")
        return rows
    raise ValueError(f"不支持的批量文件格式: {suffix}（仅支持 .csv / .json）")


def unflatten_row(row: dict[str, Any]) -> dict[str, Any]:
    """
    将 CSV 中带点号的列名展开为嵌套 dict。
    例如 user.name=Alice -> {"user": {"name": "Alice"}}
    """
    nested: dict[str, Any] = {}
    plain: dict[str, Any] = {}
    for key, value in row.items():
        if key is None:
            continue
        key = str(key).strip()
        if not key:
            continue
        parsed: Any = value
        if isinstance(value, str):
            s = value.strip()
            if s != "" and (
                s[0] in "{["
                or s in ("true", "false", "null")
                or re.fullmatch(r"-?\d+(\.\d+)?", s)
            ):
                try:
                    parsed = json.loads(s)
                except json.JSONDecodeError:
                    parsed = value
        if "." in key:
            parts = key.split(".")
            node = nested
            for p in parts[:-1]:
                nxt = node.get(p)
                if not isinstance(nxt, dict):
                    nxt = {}
                    node[p] = nxt
                node = nxt
            node[parts[-1]] = parsed
        else:
            plain[key] = parsed
    return merge_contexts(plain, nested)


def build_output_name(
    index: int,
    row: dict[str, Any],
    pattern: str,
    template_stem: str,
) -> str:
    """根据模式生成输出文件名。"""
    flat_for_name = {
        k: v for k, v in row.items() if not isinstance(v, (dict, list))
    }
    mapping = {
        "index": index,
        "index1": index + 1,
        "template": template_stem,
        **{k: str(v) for k, v in flat_for_name.items()},
    }
    try:
        name = pattern.format(**mapping)
    except KeyError as e:
        raise ValueError(f"输出文件名模式缺少字段: {e}") from e
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    return name


def cmd_render(args: argparse.Namespace) -> int:
    template_path = Path(args.template)
    if not template_path.is_file():
        print(f"错误: 模板文件不存在: {template_path}", file=sys.stderr)
        return 1

    template_text = template_path.read_text(encoding="utf-8")

    # 变量优先级（低 -> 高）：环境变量 < JSON 文件 < --vars < 批量行数据
    env_ctx: dict[str, Any] = {}
    if args.env:
        env_ctx = flatten_env_vars(prefix=None)
    if args.env_prefix:
        env_ctx = merge_contexts(env_ctx, flatten_env_vars(prefix=args.env_prefix))

    file_ctx: dict[str, Any] = {}
    if args.vars_file:
        vf = Path(args.vars_file)
        if not vf.is_file():
            print(f"错误: 变量文件不存在: {vf}", file=sys.stderr)
            return 1
        file_ctx = load_json_file(vf)

    cli_ctx: dict[str, Any] = {}
    if args.vars:
        cli_ctx = parse_vars_json(args.vars)

    base_ctx = merge_contexts(env_ctx, file_ctx, cli_ctx)

    if args.batch:
        batch_path = Path(args.batch)
        if not batch_path.is_file():
            print(f"错误: 批量数据文件不存在: {batch_path}", file=sys.stderr)
            return 1
        rows = load_batch_rows(batch_path)
        output_dir = Path(args.output_dir or "output_rendered")
        output_dir.mkdir(parents=True, exist_ok=True)
        pattern = args.output_pattern or "{template}_{index1}.txt"
        stem = template_path.stem

        written: list[str] = []
        for i, raw_row in enumerate(rows):
            row = unflatten_row(raw_row)
            ctx = merge_contexts(base_ctx, row)
            try:
                rendered = render_template(template_text, ctx, strict=args.strict)
            except Exception as e:
                print(f"错误: 第 {i + 1} 行渲染失败: {e}", file=sys.stderr)
                return 1
            out_name = build_output_name(i, row, pattern, stem)
            out_path = output_dir / out_name
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(rendered, encoding="utf-8")
            written.append(str(out_path))

        print(f"批量渲染完成: {len(written)} 个文件 -> {output_dir}")
        for p in written:
            print(f"  - {p}")
        return 0

    try:
        rendered = render_template(template_text, base_ctx, strict=args.strict)
    except Exception as e:
        print(f"错误: 渲染失败: {e}", file=sys.stderr)
        return 1

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
        print(f"已写入: {out_path}")
    else:
        sys.stdout.write(rendered)
        if not rendered.endswith("\n"):
            sys.stdout.write("\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="template_renderer.py",
        description="模板变量替换工具：支持嵌套变量、默认值、JSON/CSV 批量渲染",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python template_renderer.py --template email.txt --vars "{\\"name\\": \\"Alice\\", \\"date\\": \\"2026-08-08\\"}" --output email_out.txt
  python template_renderer.py --template email.txt --vars-file vars.json --output email_out.txt
  python template_renderer.py --template email.txt --batch users.csv --output-dir emails/ --output-pattern "mail_{name}.txt"
  python template_renderer.py --template report.txt --batch data.json --output-dir reports/
        """,
    )
    p.add_argument("--template", "-t", required=True, help="模板文件路径")
    p.add_argument(
        "--vars",
        "-v",
        default=None,
        help='命令行 JSON 变量，例如 \'{"name":"Alice","date":"2026-08-08"}\'',
    )
    p.add_argument("--vars-file", "-f", default=None, help="JSON 变量配置文件路径")
    p.add_argument(
        "--env",
        action="store_true",
        help="将全部环境变量注入模板上下文（键名原样）",
    )
    p.add_argument(
        "--env-prefix",
        default=None,
        help="仅注入带此前缀的环境变量；去掉前缀后作为键，__ 转为嵌套",
    )
    p.add_argument(
        "--output",
        "-o",
        default=None,
        help="单次渲染输出文件（省略则打印到 stdout）",
    )
    p.add_argument("--batch", "-b", default=None, help="批量数据文件（.csv 或 .json）")
    p.add_argument(
        "--output-dir",
        "-d",
        default=None,
        help="批量输出目录（默认 output_rendered）",
    )
    p.add_argument(
        "--output-pattern",
        default=None,
        help='批量输出文件名模式，默认 "{template}_{index1}.txt"',
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="严格模式：未定义变量时渲染失败",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return cmd_render(args)
    except json.JSONDecodeError as e:
        print(f"错误: JSON 解析失败: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"错误: 文件操作失败: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())