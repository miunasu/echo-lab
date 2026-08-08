"""Parser for setuptools setup.py / setup.cfg / PEP 621 pyproject.toml."""

from __future__ import annotations

import ast
import configparser
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import Dependency, DependencyGraph, Package
from .base import BaseParser
from .requirement_line import parse_requirement_line

try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None  # type: ignore


class SetuptoolsParser(BaseParser):
    """Parse setuptools/PEP 621 project metadata into a dependency graph."""

    name = "setuptools"

    def can_parse(self) -> bool:
        if self.path.is_file():
            name = self.path.name.lower()
            if name in ("setup.py", "setup.cfg"):
                return True
            if name == "pyproject.toml":
                return self._pyproject_has_project_table(self.path)
            return False
        if self.path.is_dir():
            if (self.path / "setup.py").exists() or (self.path / "setup.cfg").exists():
                return True
            pyproject = self.path / "pyproject.toml"
            if pyproject.exists() and self._pyproject_has_project_table(pyproject):
                return True
        return False

    def _pyproject_has_project_table(self, path: Path) -> bool:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return False
        if re.search(r"(?m)^\[project\]", text):
            if re.search(r"(?m)^\[tool\.poetry\]", text):
                return False
            return True
        return False

    def parse(self) -> DependencyGraph:
        graph = DependencyGraph()
        if self.path.is_file():
            root_dir = self.path.parent
            files = [self.path]
        else:
            root_dir = self.path
            files = []
            for name in ("pyproject.toml", "setup.cfg", "setup.py"):
                candidate = root_dir / name
                if candidate.exists():
                    files.append(candidate)

        if not files:
            raise FileNotFoundError(
                "No setuptools manifest under {}".format(self.path)
            )

        name = root_dir.name
        version = ""
        install_requires: List[str] = []
        extras_require: Dict[str, List[str]] = {}
        python_requires = ""

        for f in files:
            graph.source_files.append(str(f))
            if f.name == "pyproject.toml":
                n, v, reqs, extras, pyreq = self._parse_pyproject(f)
            elif f.name == "setup.cfg":
                n, v, reqs, extras, pyreq = self._parse_setup_cfg(f)
            else:
                n, v, reqs, extras, pyreq = self._parse_setup_py(f)
            if n:
                name = n
            if v:
                version = v
            install_requires.extend(reqs)
            for k, vals in extras.items():
                extras_require.setdefault(k, []).extend(vals)
            if pyreq:
                python_requires = pyreq

        root = Package(name=name, version=version, source="setuptools")
        if python_requires:
            root.metadata["python_requires"] = python_requires
        graph.add_package(root)
        graph.root = root.normalized_name

        for req in install_requires:
            dep = parse_requirement_line(req, source="install_requires")
            if dep is None:
                continue
            root.dependencies.append(dep)
            graph.add_edge(root.normalized_name, dep)
            graph.add_package(Package(name=dep.name, source="setuptools"))

        for extra_name, reqs in extras_require.items():
            dep_list: List[Dependency] = []
            for req in reqs:
                dep = parse_requirement_line(
                    req, source="extras_require:" + extra_name, optional=True
                )
                if dep is None:
                    continue
                dep_list.append(dep)
                graph.add_edge(root.normalized_name, dep)
                graph.add_package(
                    Package(name=dep.name, source="setuptools-extra:" + extra_name)
                )
            root.extras[extra_name] = dep_list
        return graph

    def _parse_pyproject(self, path: Path):
        text = path.read_text(encoding="utf-8")
        if tomllib is not None:
            data = tomllib.loads(text)
        else:
            from .poetry import _minimal_toml_parse

            data = _minimal_toml_parse(text)
        project = data.get("project") or {}
        name = project.get("name") or ""
        version = str(project.get("version") or "")
        requires = [str(x) for x in (project.get("dependencies") or [])]
        optional = project.get("optional-dependencies") or {}
        extras = {str(k): [str(x) for x in v] for k, v in optional.items()}
        pyreq = str(project.get("requires-python") or "")
        return name, version, requires, extras, pyreq

    def _parse_setup_cfg(self, path: Path):
        parser = configparser.ConfigParser()
        parser.read(str(path), encoding="utf-8")
        name = ""
        version = ""
        if parser.has_section("metadata"):
            name = parser.get("metadata", "name", fallback="")
            version = parser.get("metadata", "version", fallback="")
        requires: List[str] = []
        extras: Dict[str, List[str]] = {}
        pyreq = ""
        if parser.has_section("options"):
            raw = parser.get("options", "install_requires", fallback="")
            requires = self._split_cfg_list(raw)
            pyreq = parser.get("options", "python_requires", fallback="")
        if parser.has_section("options.extras_require"):
            for key in parser.options("options.extras_require"):
                extras[key] = self._split_cfg_list(
                    parser.get("options.extras_require", key, fallback="")
                )
        return name, version, requires, extras, pyreq

    def _split_cfg_list(self, raw: str) -> List[str]:
        items: List[str] = []
        for line in raw.replace(",", "\n").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                items.append(line)
        return items

    def _parse_setup_py(self, path: Path):
        text = path.read_text(encoding="utf-8")
        name = ""
        version = ""
        requires: List[str] = []
        extras: Dict[str, List[str]] = {}
        pyreq = ""
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return self._parse_setup_py_regex(text)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            func_name = ""
            if isinstance(func, ast.Name):
                func_name = func.id
            elif isinstance(func, ast.Attribute):
                func_name = func.attr
            if func_name != "setup":
                continue
            for kw in node.keywords:
                if kw.arg == "name":
                    name = self._literal_str(kw.value) or name
                elif kw.arg == "version":
                    version = self._literal_str(kw.value) or version
                elif kw.arg == "install_requires":
                    requires = self._literal_str_list(kw.value)
                elif kw.arg == "extras_require":
                    extras = self._literal_extras(kw.value)
                elif kw.arg == "python_requires":
                    pyreq = self._literal_str(kw.value) or pyreq
        if not requires and not name:
            return self._parse_setup_py_regex(text)
        return name, version, requires, extras, pyreq

    def _parse_setup_py_regex(self, text: str):
        name_m = re.search(r"""name\s*=\s*['"]([^'"]+)['"]""", text)
        ver_m = re.search(r"""version\s*=\s*['"]([^'"]+)['"]""", text)
        name = name_m.group(1) if name_m else ""
        version = ver_m.group(1) if ver_m else ""
        requires: List[str] = []
        extras: Dict[str, List[str]] = {}
        block = re.search(r"install_requires\s*=\s*\[(.*?)\]", text, re.S)
        if block:
            requires = re.findall(r['"]([^"']+)['"]', block.group(1))
        py_m = re.search(r"""python_requires\s*=\s*['"]([^'"]+)['"]""", text)
        pyreq = py_m.group(1) if py_m else ""
        return name, version, requires, extras, pyreq

    def _literal_str(self, node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    def _literal_str_list(self, node: ast.AST) -> List[str]:
        if isinstance(node, (ast.List, ast.Tuple)):
            out: List[str] = []
            for elt in node.elts:
                s = self._literal_str(elt)
                if s is not None:
                    out.append(s)
            return out
        return []

    def _literal_extras(self, node: ast.AST) -> Dict[str, List[str]]:
        if not isinstance(node, ast.Dict):
            return {}
        result: Dict[str, List[str]] = {}
        for k, v in zip(node.keys, node.values):
            if k is None:
                continue
            key = self._literal_str(k)
            if key is None:
                continue
            result[key] = self._literal_str_list(v)
        return result