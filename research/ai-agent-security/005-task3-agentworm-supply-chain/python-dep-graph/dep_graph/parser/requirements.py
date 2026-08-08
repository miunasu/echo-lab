"""Parser for requirements.txt and related pip requirement files."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Set

from ..models import Dependency, DependencyGraph, Package
from .base import BaseParser
from .requirement_line import parse_requirement_line


class RequirementsParser(BaseParser):
    """Parse pip-style requirements files into a dependency graph."""

    name = "requirements"

    def __init__(self, path: str, root_name: Optional[str] = None):
        super().__init__(path)
        self.root_name = root_name

    def can_parse(self) -> bool:
        p = self.path
        if p.is_file():
            name = p.name.lower()
            if name.endswith(".txt") or name.endswith(".in"):
                return True
            if "requirements" in name:
                return True
            return False
        if p.is_dir():
            candidates = list(p.glob("requirements*.txt")) + list(
                p.glob("requirements*.in")
            )
            return len(candidates) > 0
        return False

    def _resolve_file(self) -> Path:
        if self.path.is_file():
            return self.path
        for pattern in ("requirements.txt", "requirements.in", "requirements-dev.txt"):
            candidate = self.path / pattern
            if candidate.exists():
                return candidate
        found = sorted(self.path.glob("requirements*.txt"), key=lambda x: len(x.name))
        if found:
            return found[0]
        raise FileNotFoundError("No requirements file under {}".format(self.path))

    def parse(self) -> DependencyGraph:
        req_file = self._resolve_file()
        graph = DependencyGraph(source_files=[str(req_file)])
        project_name = self.root_name or (
            self.path.name if self.path.is_dir() else self.path.parent.name
        )
        root = self._ensure_root(graph, project_name, "requirements")

        visited: Set[str] = set()
        deps = self._parse_file(req_file, visited)
        root.dependencies.extend(deps)
        for dep in deps:
            graph.add_edge(root.normalized_name, dep)
            version = ""
            if dep.version_spec.startswith("=="):
                version = dep.version_spec[2:].strip()
            pkg = Package(
                name=dep.name,
                version=version,
                source="requirements",
                metadata={"declared_by": root.normalized_name},
            )
            graph.add_package(pkg)
        return graph

    def _parse_file(self, file_path: Path, visited: Set[str]) -> List[Dependency]:
        key = str(file_path.resolve())
        if key in visited:
            return []
        visited.add(key)

        deps: List[Dependency] = []
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = file_path.read_text(encoding="latin-1")

        for lineno, line in enumerate(text.splitlines(), 1):
            source = "{}:{}".format(file_path.name, lineno)
            try:
                dep = parse_requirement_line(line, source=source)
            except ValueError as exc:
                msg = str(exc)
                if msg.startswith("INCLUDE_REQ:") or msg.startswith(
                    "INCLUDE_CONSTRAINT:"
                ):
                    rel = msg.split(":", 1)[1]
                    included = (file_path.parent / rel).resolve()
                    if included.exists():
                        deps.extend(self._parse_file(included, visited))
                    continue
                raise
            if dep is not None:
                deps.append(dep)
        return deps