# template_renderer

基于 Jinja2 的模板变量替换 CLI 工具，适用于邮件模板、报告自动化、批量文档生成。

## 安装

```bash
pip install -r requirements.txt
```

依赖：`jinja2>=3.1.0`

## 快速开始

模板 `examples/email.txt`：

```text
Dear {{name|default:"Anonymous"}},
Your report for {{date}} is ready.
```

单次渲染：

```bash
python template_renderer.py --template examples/email.txt --vars "{\"name\": \"Alice\", \"date\": \"2026-08-08\"}" --output email_out.txt
```

渲染结果：

```text
Dear Alice,
Your report for 2026-08-08 is ready.
```

## 功能一览

| 能力 | 说明 |
|------|------|
| 占位符 | `{{name}}`、`{{user.name}}` 等 |
| 默认值 | `{{name\|default:"Anonymous"}}`（兼容 Jinja2 标准 `default("x")`） |
| 变量来源 | `--vars` JSON、`--vars-file`、环境变量（`--env` / `--env-prefix`） |
| 批量渲染 | `--batch users.csv` 或 `users.json` + `--output-dir` |
| 严格模式 | `--strict`：未定义变量直接失败 |

变量优先级（低 -> 高）：

1. 环境变量（`--env` / `--env-prefix`）
2. `--vars-file` JSON 文件
3. `--vars` 命令行 JSON
4. 批量行数据（`--batch` 每一行）

## CLI 参数

```text
python template_renderer.py --template <模板>
    [--vars JSON]
    [--vars-file 文件.json]
    [--env]
    [--env-prefix 前缀]
    [--output 输出文件]          # 单次模式；省略则打印到 stdout
    [--batch 数据.csv|json]
    [--output-dir 目录]          # 批量模式输出目录
    [--output-pattern 模式]      # 默认 {template}_{index1}.txt
    [--strict]
```

### 输出文件名模式

批量模式可用占位：

- `{index}`：从 0 开始
- `{index1}`：从 1 开始
- `{template}`：模板文件名（不含扩展名）
- 行内顶层字段，如 `{name}`、`{id}`

示例：`--output-pattern "mail_{name}.txt"`

## 使用示例

### 1. 命令行 JSON 变量

```bash
python template_renderer.py ^
  --template examples/email.txt ^
  --vars "{\"name\": \"Alice\", \"date\": \"2026-08-08\", \"id\": \"1001\", \"user\": {\"name\": \"Alice Wong\"}}" ^
  --output examples/emails/email_out.txt
```

### 2. JSON 配置文件

```bash
python template_renderer.py -t examples/email.txt -f examples/vars.json -o out.txt
```

### 3. 环境变量

前缀模式（推荐）。`TR_` 前缀会被去掉；双下划线 `__` 表示嵌套：

```powershell
$env:TR_NAME = "EnvUser"
$env:TR_DATE = "2026-01-01"
$env:TR_USER__NAME = "From Env"
python template_renderer.py -t examples/email.txt --env-prefix TR_ -o out.txt
```

等价上下文：

```json
{"name": "EnvUser", "date": "2026-01-01", "user": {"name": "From Env"}}
```

### 4. 批量 CSV

`examples/users.csv` 支持点号列名展开嵌套，例如 `user.name`、`manager.name`：

```bash
python template_renderer.py ^
  --template examples/email.txt ^
  --batch examples/users.csv ^
  --output-dir examples/emails/batch_csv ^
  --output-pattern "mail_{name}.txt"
```

### 5. 批量 JSON

支持「对象数组」或 `{"items": [ ... ]}`：

```bash
python template_renderer.py ^
  --template examples/report.txt ^
  --batch examples/users.json ^
  --output-dir examples/emails/batch_json ^
  --output-pattern "report_{id}.txt"
```

## 模板语法说明

本工具在渲染前会把：

```text
{{name|default:"Anonymous"}}
{{user.name|default:'N/A'}}
```

自动转换为 Jinja2 标准写法：

```text
{{ name|default("Anonymous") }}
{{ user.name|default('N/A') }}
```

同时也直接支持全部 Jinja2 表达式（条件、循环、过滤器等）。非严格模式下使用 `ChainableUndefined`，因此父对象缺失时 `{{user.name|default("N/A")}}` 仍可安全回落默认值。

## 目录结构

```text
output/template_renderer/
  template_renderer.py    # 主程序
  requirements.txt
  README.md
  examples/
    email.txt             # 邮件模板
    report.txt            # 报告模板
    vars.json             # 单次变量示例
    users.csv             # 批量 CSV
    users.json            # 批量 JSON
    emails/               # 渲染输出示例
```

## 验证结果摘要

已本地验证：

- 单次 `--vars` / `--vars-file` 渲染正确
- 缺省变量回落 `Anonymous` / `N/A` / `0`
- CSV 批量生成 3 封邮件（Alice/Bob/Carol）
- JSON 批量生成 2 份报告
- `--env-prefix TR_` 注入嵌套环境变量成功