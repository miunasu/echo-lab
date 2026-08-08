# py-package-builder

Automated Python package scaffolding and wheel builder.

Quickly create a standard Python package layout (`setup.py` / `pyproject.toml` / `__init__.py`),
configure metadata (name, version, author, dependencies, entry points, custom modules),
build a **wheel** (`bdist_wheel`), and verify project structure integrity.

## Features

1. **init** - Generate standard package structure from CLI flags or a TOML/JSON config
2. **Metadata** - name, version, author, email, license, dependencies, optional deps, URLs
3. **build** - Build wheel distributions (PEP 517 via `python -m build`, with setuptools fallback)
4. **verify** - Validate package layout, metadata, modules, entry points, and wheel contents
5. **Custom modules & entry points** - inject module source and console_scripts

## Install

```bash
cd output/py-package-builder
pip install -e .
# optional TOML write helpers on older Python:
pip install -e ".[toml]"
# build backend used by `build` command:
pip install build wheel setuptools
```

After install, the CLIs `py-package-builder` and `ppb` are available. You can also run:

```bash
python -m py_package_builder --help
```

## CLI

### init - scaffold a package

```bash
# From flags
py-package-builder init -n demo_pkg -a Alice -v 0.1.0 -o ./demo_pkg --dep "requests>=2.0"

# Extra modules and entry points
py-package-builder init -n demo_pkg -o ./demo_pkg --module utils --entry "demo-pkg=demo_pkg.cli:main"

# From config template
py-package-builder init -c examples/sample.package.builder.toml -o ./demo_hello --force
```

Generated layout (example):

```text
demo_pkg/
  demo_pkg/
    __init__.py
    core.py
    cli.py
  tests/
    test_smoke.py
  pyproject.toml
  setup.py
  README.md
  LICENSE
  MANIFEST.in
  package.builder.toml
```

### build - produce wheel

```bash
py-package-builder build -p ./demo_pkg
py-package-builder build -p ./demo_pkg --sdist -o ./demo_pkg/dist
```

Artifacts land in `<project>/dist/*.whl` by default.

### verify - structure & wheel checks

```bash
py-package-builder verify -p ./demo_pkg
py-package-builder verify -p ./demo_pkg -w ./demo_pkg/dist/some.whl --json
```

## Config format

See `examples/sample.package.builder.toml` and `examples/sample.package.builder.json`.

TOML sketch:

```toml
[package]
name = "demo_hello"
version = "0.1.0"
author = "Alice"
dependencies = ["click>=8.0"]
use_pyproject = true
use_setup_py = true

[[modules]]
name = "core"
content = """
def hello(name: str = "world") -> str:
    return f"Hello, {name}!"
"""

[[entry_points]]
name = "demo-hello"
module = "demo_hello.cli"
attr = "main"
```

## Python API

```python
from py_package_builder.core import (
    PackageConfig,
    PackageGenerator,
    PackageBuilder,
    PackageVerifier,
    load_config,
)
from py_package_builder.core.config import default_config

cfg = default_config(name="api_demo", author="Spore")
PackageGenerator(cfg, "./api_demo").generate(force=True)
result = PackageBuilder("./api_demo").build()
report = PackageVerifier("./api_demo").verify()
assert report.ok
```

## Project layout (this tool)

```text
py-package-builder/
  py_package_builder/
    __init__.py
    __main__.py
    cli.py
    commands/
      init_cmd.py
      build_cmd.py
      verify_cmd.py
    core/
      config.py
      generator.py
      builder.py
      verifier.py
  examples/
  tests/
  pyproject.toml
  setup.py
  README.md
```

## Requirements

- Python >= 3.8
- `setuptools`, `wheel`, `build` (for building wheels)
- `tomli` on Python < 3.11 when reading TOML configs

## License

MIT