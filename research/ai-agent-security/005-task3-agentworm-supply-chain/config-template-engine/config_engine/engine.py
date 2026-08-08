"""Jinja2-based template rendering engine for config files."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    Undefined,
    Template,
    TemplateError,
    TemplateNotFound,
    select_autoescape,
)


SUPPORTED_FORMATS = ("yaml", "yml", "json", "md", "markdown")


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_templates_dir() -> Path:
    return _project_root() / "templates"


class TemplateEngine:
    """Core Jinja2 template engine with multi-format output support."""

    def __init__(
        self,
        template_dirs: Optional[List[Union[str, Path]]] = None,
        strict: bool = True,
        extra_globals: Optional[Dict[str, Any]] = None,
    ) -> None:
        dirs: List[str] = []
        if template_dirs:
            dirs.extend(str(Path(d).resolve()) for d in template_dirs)
        default = default_templates_dir()
        if default.exists() and str(default) not in dirs:
            dirs.append(str(default))
        if not dirs:
            dirs.append(str(Path.cwd()))

        undefined = StrictUndefined if strict else Undefined
        self.env = Environment(
            loader=FileSystemLoader(dirs, followlinks=True),
            undefined=undefined,
            autoescape=select_autoescape(enabled_extensions=()),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )
        self._register_filters()
        if extra_globals:
            self.env.globals.update(extra_globals)
        self.template_dirs = dirs

    def _register_filters(self) -> None:
        self.env.filters["to_json"] = lambda v, indent=2: json.dumps(
            v, indent=indent, ensure_ascii=False, default=str
        )
        self.env.filters["to_yaml"] = lambda v, indent=2: yaml.safe_dump(
            v,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            indent=indent,
        ).rstrip()
        self.env.filters["upper"] = lambda v: str(v).upper()
        self.env.filters["lower"] = lambda v: str(v).lower()
        self.env.filters["default_if_none"] = lambda v, d="": d if v is None else v
        self.env.filters["env_or"] = (
            lambda key, default="": os.environ.get(str(key), default)
        )

    def list_templates(self, extensions: Optional[List[str]] = None) -> List[str]:
        return sorted(set(self.env.list_templates()))

    def get_template(self, name: str) -> Template:
        try:
            return self.env.get_template(name)
        except TemplateNotFound as exc:
            raise FileNotFoundError(
                f"Template not found: {name}. Search paths: {self.template_dirs}"
            ) from exc

    def render_string(self, source: str, context: Optional[Dict[str, Any]] = None) -> str:
        context = context or {}
        try:
            template = self.env.from_string(source)
            return template.render(**context)
        except TemplateError as exc:
            raise ValueError(f"Template render error: {exc}") from exc

    def render_file(
        self,
        template_name: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        context = context or {}
        try:
            template = self.get_template(template_name)
            return template.render(**context)
        except TemplateError as exc:
            raise ValueError(f"Template render error in '{template_name}': {exc}") from exc

    def render_path(
        self,
        template_path: Union[str, Path],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        path = Path(template_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Template file not found: {path}")
        source = path.read_text(encoding="utf-8")
        return self.render_string(source, context)


class ConfigRenderer:
    """High-level renderer that produces YAML / JSON / Markdown configs."""

    def __init__(self, engine: Optional[TemplateEngine] = None) -> None:
        self.engine = engine or TemplateEngine()

    @staticmethod
    def detect_format(path_or_name: str, explicit: Optional[str] = None) -> str:
        if explicit:
            fmt = explicit.lower().lstrip(".")
            if fmt == "yml":
                return "yaml"
            if fmt == "markdown":
                return "md"
            if fmt not in SUPPORTED_FORMATS:
                raise ValueError(
                    f"Unsupported format: {explicit}. Use one of {SUPPORTED_FORMATS}"
                )
            return fmt

        name = path_or_name.lower()
        for suffix in (".j2", ".jinja2", ".jinja"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        if name.endswith((".yaml", ".yml")):
            return "yaml"
        if name.endswith(".json"):
            return "json"
        if name.endswith((".md", ".markdown")):
            return "md"
        return "yaml"

    @staticmethod
    def load_context(path: Union[str, Path]) -> Dict[str, Any]:
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"Context file not found: {path}")
        text = path.read_text(encoding="utf-8")
        suffix = path.suffix.lower()
        if suffix in (".yaml", ".yml"):
            data = yaml.safe_load(text) or {}
        elif suffix == ".json":
            data = json.loads(text or "{}")
        else:
            try:
                data = yaml.safe_load(text) or {}
            except yaml.YAMLError:
                data = json.loads(text or "{}")
        if not isinstance(data, dict):
            raise ValueError(
                f"Context must be a mapping/object, got {type(data).__name__}"
            )
        return data

    def render(
        self,
        template: str,
        context: Optional[Dict[str, Any]] = None,
        output_format: Optional[str] = None,
        from_string: bool = False,
    ) -> str:
        context = dict(context or {})
        context.setdefault("env", dict(os.environ))

        if from_string:
            raw = self.engine.render_string(template, context)
            fmt = self.detect_format("output.yaml", output_format)
        else:
            path = Path(template)
            if path.is_file():
                raw = self.engine.render_path(path, context)
                fmt = self.detect_format(str(path), output_format)
            else:
                raw = self.engine.render_file(template, context)
                fmt = self.detect_format(template, output_format)

        return self._normalize_output(raw, fmt)

    def _normalize_output(self, raw: str, fmt: str) -> str:
        text = raw.strip("\n") + "\n"
        if fmt == "json":
            try:
                data = json.loads(text)
                return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
            except json.JSONDecodeError:
                return text if text.endswith("\n") else text + "\n"
        if fmt == "yaml":
            try:
                data = yaml.safe_load(text)
                if data is not None:
                    return yaml.safe_dump(
                        data,
                        default_flow_style=False,
                        allow_unicode=True,
                        sort_keys=False,
                    )
            except yaml.YAMLError:
                return text if text.endswith("\n") else text + "\n"
            return text if text.endswith("\n") else text + "\n"
        return text if text.endswith("\n") else text + "\n"

    def render_to_file(
        self,
        template: str,
        output_path: Union[str, Path],
        context: Optional[Dict[str, Any]] = None,
        output_format: Optional[str] = None,
        from_string: bool = False,
    ) -> Path:
        out = Path(output_path)
        fmt = output_format or self.detect_format(str(out))
        content = self.render(
            template=template,
            context=context,
            output_format=fmt,
            from_string=from_string,
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        return out