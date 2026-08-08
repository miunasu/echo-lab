"""Generate standard Python package project structure from PackageConfig."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Dict, List

from .config import PackageConfig


class PackageGenerator:
    """Scaffold a Python package project on disk."""

    def __init__(self, config: PackageConfig, target_dir: str | Path):
        self.config = config
        self.target_dir = Path(target_dir).resolve()
        self.import_name = config.import_name()
        self.created: List[str] = []
        self.updated: List[str] = []

    def generate(self, force: bool = False) -> Dict[str, List[str]]:
        """
        Create package layout.

        Returns dict with keys: created, updated, skipped.
        """
        self.created = []
        self.updated = []
        skipped: List[str] = []

        self.target_dir.mkdir(parents=True, exist_ok=True)

        files = self._plan_files()
        for rel_path, content in files.items():
            path = self.target_dir / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and not force:
                skipped.append(str(rel_path))
                continue
            existed = path.exists()
            path.write_text(content, encoding="utf-8")
            if existed:
                self.updated.append(str(rel_path))
            else:
                self.created.append(str(rel_path))

        return {
            "created": list(self.created),
            "updated": list(self.updated),
            "skipped": skipped,
        }

    def _plan_files(self) -> Dict[str, str]:
        cfg = self.config
        pkg = self.import_name
        files: Dict[str, str] = {}

        files[f"{pkg}/__init__.py"] = textwrap.dedent(
            f'''\
            """{cfg.description}"""

            __version__ = "{cfg.version}"
            __author__ = "{cfg.author}"

            __all__ = ["__version__", "__author__"]
            '''
        )

        for mod in cfg.modules:
            files[f"{pkg}/{mod.name}.py"] = (
                mod.content if mod.content.endswith("\n") else mod.content + "\n"
            )

        if any(
            ep.module.endswith(".cli") or ep.module == f"{pkg}.cli"
            for ep in cfg.entry_points
        ):
            if f"{pkg}/cli.py" not in files:
                files[f"{pkg}/cli.py"] = self._cli_module()

        if cfg.use_pyproject:
            files["pyproject.toml"] = self._pyproject_toml()

        if cfg.use_setup_py:
            files["setup.py"] = self._setup_py()

        if cfg.include_readme:
            files["README.md"] = self._readme()

        if cfg.include_license:
            files["LICENSE"] = self._license_text()

        files["MANIFEST.in"] = textwrap.dedent(
            f"""\
            include README.md
            include LICENSE
            include pyproject.toml
            recursive-include {pkg} *.py
            """
        )

        files["tests/__init__.py"] = ""
        files["tests/test_smoke.py"] = textwrap.dedent(
            f'''\
            """Smoke tests for {cfg.name}."""

            def test_import():
                import {pkg}
                assert {pkg}.__version__ == "{cfg.version}"
            '''
        )

        return files

    def _cli_module(self) -> str:
        cfg = self.config
        pkg = self.import_name
        has_core = any(m.name == "core" for m in cfg.modules)
        body = (
            f"    from {pkg}.core import hello\n    print(hello())\n"
            if has_core
            else f'    print("{cfg.name} v{cfg.version}")\n'
        )
        return textwrap.dedent(
            f'''\
            """Command-line entry for {cfg.name}."""

            from __future__ import annotations


            def main() -> None:
            {body}

            if __name__ == "__main__":
                main()
            '''
        )

    def _pyproject_toml(self) -> str:
        cfg = self.config
        pkg = self.import_name

        def _toml_str_array(items, multiline: bool = False) -> str:
            if not items:
                return "[]"
            if not multiline:
                return "[" + ", ".join(f'"{i}"' for i in items) + "]"
            body = ",\n".join(f'    "{i}"' for i in items)
            return "[\n" + body + ",\n]"

        optional_section = ""
        if cfg.optional_dependencies:
            lines = ["", "[project.optional-dependencies]"]
            for extra, items in cfg.optional_dependencies.items():
                lines.append(f"{extra} = {_toml_str_array(items, multiline=bool(items))}")
            optional_section = "\n".join(lines) + "\n"

        scripts_section = ""
        if cfg.entry_points:
            lines = ["", "[project.scripts]"]
            for ep in cfg.entry_points:
                lines.append(f'{ep.name} = "{ep.module}:{ep.attr}"')
            scripts_section = "\n".join(lines) + "\n"

        urls_section = ""
        if cfg.urls:
            lines = ["", "[project.urls]"]
            for k, v in cfg.urls.items():
                lines.append(f'{k} = "{v}"')
            urls_section = "\n".join(lines) + "\n"

        authors = f'{{name = "{cfg.author}"'
        if cfg.author_email:
            authors += f', email = "{cfg.author_email}"'
        authors += "}"

        # PEP 639: license expressions supersede License :: classifiers
        classifiers = [
            c for c in (cfg.classifiers or [])
            if not str(c).startswith("License ::")
        ]

        parts = [
            "[build-system]",
            'requires = ["setuptools>=61", "wheel"]',
            'build-backend = "setuptools.build_meta"',
            "",
            "[project]",
            f'name = "{cfg.name}"',
            f'version = "{cfg.version}"',
            f'description = "{cfg.description}"',
            'readme = "README.md"',
            f'license = "{cfg.license}"',
            f'requires-python = "{cfg.python_requires}"',
            "authors = [",
            f"    {authors},",
            "]",
            f"keywords = {_toml_str_array(cfg.keywords)}",
            f"classifiers = {_toml_str_array(classifiers, multiline=bool(classifiers))}",
            f"dependencies = {_toml_str_array(cfg.dependencies, multiline=bool(cfg.dependencies))}",
            optional_section.rstrip("\n"),
            scripts_section.rstrip("\n"),
            urls_section.rstrip("\n"),
            "",
            "[tool.setuptools.packages.find]",
            'where = ["."]',
            f'include = ["{pkg}*"]',
            "",
        ]
        text = "\n".join(parts)
        while "\n\n\n" in text:
            text = text.replace("\n\n\n", "\n\n")
        return text.rstrip() + "\n"

    def _setup_py(self) -> str:
        cfg = self.config
        # Prefer a thin setup.py when pyproject.toml is also generated, to avoid
        # metadata conflicts with modern setuptools (PEP 621 / PEP 639).
        if cfg.use_pyproject:
            return textwrap.dedent(
                f'''\
                #!/usr/bin/env python
                """Thin setup wrapper for {cfg.name}; metadata lives in pyproject.toml."""

                from setuptools import setup

                setup()
                '''
            )

        pkg = self.import_name
        deps = repr(cfg.dependencies)
        eps = [ep.as_script() for ep in cfg.entry_points]
        entry = repr({"console_scripts": eps}) if eps else "{}"
        return textwrap.dedent(
            f'''\
            #!/usr/bin/env python
            """Setup script for {cfg.name}."""

            from setuptools import setup, find_packages

            setup(
                name="{cfg.name}",
                version="{cfg.version}",
                description="{cfg.description}",
                author="{cfg.author}",
                author_email="{cfg.author_email}",
                license="{cfg.license}",
                python_requires="{cfg.python_requires}",
                packages=find_packages(include=["{pkg}", "{pkg}.*"]),
                install_requires={deps},
                entry_points={entry},
                include_package_data=True,
                zip_safe=False,
            )
            '''
        )

    def _readme(self) -> str:
        cfg = self.config
        ep_lines = "\n".join(
            f"- `{ep.name}` -> `{ep.module}:{ep.attr}`" for ep in cfg.entry_points
        )
        if not ep_lines:
            ep_lines = "- (none)"
        deps = "\n".join(f"- `{d}`" for d in cfg.dependencies) or "- (none)"
        return textwrap.dedent(
            f"""\
            # {cfg.name}

            {cfg.description}

            ## Install

            ```bash
            pip install .
            # or from wheel
            pip install dist/{cfg.name.replace('-', '_')}-{cfg.version}-*.whl
            ```

            ## Entry points

            {ep_lines}

            ## Dependencies

            {deps}

            ## Develop

            ```bash
            pip install -e .
            python -m {self.import_name}
            ```

            ---
            Generated by **py-package-builder**.
            """
        )

    def _license_text(self) -> str:
        cfg = self.config
        if cfg.license.upper() == "MIT":
            return textwrap.dedent(
                f"""\
                MIT License

                Copyright (c) 2026 {cfg.author}

                Permission is hereby granted, free of charge, to any person obtaining a copy
                of this software and associated documentation files (the "Software"), to deal
                in the Software without restriction, including without limitation the rights
                to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
                copies of the Software, and to permit persons to whom the Software is
                furnished to do so, subject to the following conditions:

                The above copyright notice and this permission notice shall be included in all
                copies or substantial portions of the Software.

                THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
                IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
                FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
                AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
                LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
                OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
                SOFTWARE.
                """
            )
        return f"License: {cfg.license}\nCopyright (c) {cfg.author}\n"