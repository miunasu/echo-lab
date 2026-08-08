#!/usr/bin/env python3
"""Example: batch-render configs for multiple environments."""

from pathlib import Path

from config_engine import ConfigRenderer, SchemaValidator

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "examples" / "generated"
OUT.mkdir(parents=True, exist_ok=True)

renderer = ConfigRenderer()
validator = SchemaValidator()

jobs = [
    ("logging/logging.yaml.j2", "dev.context.yaml", "logging", "logging.dev.yaml"),
    ("logging/logging.yaml.j2", "prod.context.yaml", "logging", "logging.prod.yaml"),
    ("database/database.yaml.j2", "dev.context.yaml", "database", "database.dev.yaml"),
    ("database/database.yaml.j2", "prod.context.yaml", "database", "database.prod.yaml"),
    ("api/api.yaml.j2", "dev.context.yaml", "api", "api.dev.yaml"),
    ("api/api.yaml.j2", "prod.context.yaml", "api", "api.prod.yaml"),
    ("api/api.json.j2", "dev.context.yaml", "api", "api.dev.json"),
    ("logging/logging.md.j2", "dev.context.yaml", None, "logging.dev.md"),
]

for template, ctx_name, schema, out_name in jobs:
    ctx = renderer.load_context(ROOT / "examples" / ctx_name)
    out_path = OUT / out_name
    renderer.render_to_file(template, out_path, context=ctx)
    status = "rendered"
    if schema:
        result = validator.validate(out_path, schema)
        status = "OK" if result.ok else f"INVALID: {result.summary()}"
    print(f"{out_name}: {status}")

print(f"\nOutput directory: {OUT}")