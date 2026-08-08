"""Schema validator for rendered configuration files."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from jsonschema import Draft202012Validator, ValidationError


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_schemas_dir() -> Path:
    return _project_root() / "schemas"


@dataclass
class ValidationIssue:
    path: str
    message: str
    validator: str = ""
    schema_path: str = ""

    def __str__(self) -> str:
        loc = self.path or "(root)"
        extra = f" [{self.validator}]" if self.validator else ""
        return f"{loc}: {self.message}{extra}"


@dataclass
class ValidationResult:
    ok: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    data: Any = None
    schema_name: str = ""

    def summary(self) -> str:
        if self.ok:
            return "Validation passed."
        lines = [f"Validation failed with {len(self.issues)} issue(s):"]
        for i, issue in enumerate(self.issues, 1):
            lines.append(f"  {i}. {issue}")
        return "\n".join(lines)


class SchemaValidator:
    """Validate config data (dict / file) against JSON Schema documents."""

    def __init__(self, schema_dirs: Optional[List[Union[str, Path]]] = None) -> None:
        self.schema_dirs: List[Path] = []
        if schema_dirs:
            self.schema_dirs.extend(Path(d).resolve() for d in schema_dirs)
        default = default_schemas_dir()
        if default.exists() and default not in self.schema_dirs:
            self.schema_dirs.append(default)
        self._cache: Dict[str, Dict[str, Any]] = {}

    def list_schemas(self) -> List[str]:
        names: List[str] = []
        for d in self.schema_dirs:
            if not d.is_dir():
                continue
            for p in sorted(d.rglob("*.json")):
                names.append(str(p.relative_to(d)).replace("\\", "/"))
            for p in sorted(d.rglob("*.yaml")):
                names.append(str(p.relative_to(d)).replace("\\", "/"))
            for p in sorted(d.rglob("*.yml")):
                names.append(str(p.relative_to(d)).replace("\\", "/"))
        return names

    def load_schema(self, schema_ref: Union[str, Path, Dict[str, Any]]) -> Dict[str, Any]:
        if isinstance(schema_ref, dict):
            return schema_ref

        path = Path(schema_ref)
        if path.is_file():
            return self._load_schema_file(path)

        key = str(schema_ref).replace("\\", "/")
        if key in self._cache:
            return self._cache[key]

        candidates = [key]
        if not key.endswith((".json", ".yaml", ".yml")):
            candidates.extend([f"{key}.json", f"{key}.yaml", f"{key}.yml"])

        for d in self.schema_dirs:
            for cand in candidates:
                p = d / cand
                if p.is_file():
                    schema = self._load_schema_file(p)
                    self._cache[key] = schema
                    return schema

        raise FileNotFoundError(
            f"Schema not found: {schema_ref}. Search paths: {[str(d) for d in self.schema_dirs]}"
        )

    def _load_schema_file(self, path: Path) -> Dict[str, Any]:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            data = json.loads(text)
        else:
            data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError(f"Schema must be an object: {path}")
        return data

    @staticmethod
    def load_config(source: Union[str, Path, Dict[str, Any], list]) -> Any:
        if isinstance(source, (dict, list)):
            return source
        path = Path(source)
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            suffix = path.suffix.lower()
            if suffix == ".json":
                return json.loads(text)
            if suffix in (".yaml", ".yml"):
                return yaml.safe_load(text)
            try:
                return yaml.safe_load(text)
            except yaml.YAMLError:
                return json.loads(text)
        text = str(source)
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError:
            return json.loads(text)

    def validate(
        self,
        config: Union[str, Path, Dict[str, Any], list],
        schema: Union[str, Path, Dict[str, Any]],
    ) -> ValidationResult:
        try:
            data = self.load_config(config)
        except Exception as exc:
            return ValidationResult(
                ok=False,
                issues=[
                    ValidationIssue(
                        path="(parse)", message=f"Failed to parse config: {exc}"
                    )
                ],
                schema_name=str(schema) if not isinstance(schema, dict) else "(inline)",
            )

        try:
            schema_obj = self.load_schema(schema)
        except Exception as exc:
            return ValidationResult(
                ok=False,
                issues=[
                    ValidationIssue(
                        path="(schema)", message=f"Failed to load schema: {exc}"
                    )
                ],
                data=data,
                schema_name=str(schema) if not isinstance(schema, dict) else "(inline)",
            )

        validator = Draft202012Validator(schema_obj)
        issues: List[ValidationIssue] = []
        for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
            path = ".".join(str(p) for p in err.absolute_path)
            issues.append(
                ValidationIssue(
                    path=path,
                    message=err.message,
                    validator=err.validator or "",
                    schema_path=".".join(str(p) for p in err.schema_path),
                )
            )

        schema_name = (
            schema
            if isinstance(schema, str)
            else (str(schema) if isinstance(schema, Path) else "(inline)")
        )
        return ValidationResult(
            ok=len(issues) == 0,
            issues=issues,
            data=data,
            schema_name=str(schema_name),
        )

    def validate_or_raise(
        self,
        config: Union[str, Path, Dict[str, Any], list],
        schema: Union[str, Path, Dict[str, Any]],
    ) -> Any:
        result = self.validate(config, schema)
        if not result.ok:
            raise ValidationError(result.summary())
        return result.data