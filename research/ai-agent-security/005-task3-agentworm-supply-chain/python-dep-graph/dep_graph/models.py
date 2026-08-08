"""Core data models for dependency graph analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


def normalize_name(name: str) -> str:
    """Normalize package name per PEP 503."""
    return name.strip().lower().replace("_", "-").replace(".", "-")


@dataclass(frozen=True)
class Dependency:
    """A single dependency edge from one package to another."""

    name: str
    version_spec: str = ""
    extras: Tuple[str, ...] = ()
    markers: str = ""
    source: str = ""
    optional: bool = False

    @property
    def normalized_name(self) -> str:
        return normalize_name(self.name)


@dataclass
class Package:
    """A package node in the dependency graph."""

    name: str
    version: str = ""
    dependencies: List[Dependency] = field(default_factory=list)
    source: str = ""
    extras: Dict[str, List[Dependency]] = field(default_factory=dict)
    metadata: Dict[str, str] = field(default_factory=dict)

    @property
    def normalized_name(self) -> str:
        return normalize_name(self.name)


@dataclass
class VersionConflict:
    """Detected version constraint conflict for the same package."""

    package: str
    constraints: List[Tuple[str, str]]
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "package": self.package,
            "constraints": [
                {"requirer": r, "version_spec": v} for r, v in self.constraints
            ],
            "message": self.message
            or "Conflicting version requirements for {}".format(self.package),
        }


@dataclass
class Cycle:
    """A cyclic dependency path."""

    nodes: List[str]

    def to_dict(self) -> dict:
        return {
            "nodes": self.nodes,
            "path": " -> ".join(self.nodes + [self.nodes[0]]),
        }


@dataclass
class DependencyGraph:
    """Directed dependency graph with analysis helpers."""

    packages: Dict[str, Package] = field(default_factory=dict)
    edges: Dict[str, Set[str]] = field(default_factory=dict)
    reverse_edges: Dict[str, Set[str]] = field(default_factory=dict)
    edge_meta: Dict[Tuple[str, str], Dependency] = field(default_factory=dict)
    root: Optional[str] = None
    source_files: List[str] = field(default_factory=list)

    def add_package(self, package: Package) -> None:
        key = package.normalized_name
        if key in self.packages:
            existing = self.packages[key]
            if package.version and not existing.version:
                existing.version = package.version
            existing.dependencies.extend(package.dependencies)
            for extra, deps in package.extras.items():
                existing.extras.setdefault(extra, []).extend(deps)
            existing.metadata.update(package.metadata)
        else:
            self.packages[key] = package
            self.edges.setdefault(key, set())
            self.reverse_edges.setdefault(key, set())

    def add_edge(self, from_pkg: str, dependency: Dependency) -> None:
        src = normalize_name(from_pkg)
        dst = dependency.normalized_name
        self.edges.setdefault(src, set()).add(dst)
        self.reverse_edges.setdefault(dst, set()).add(src)
        self.edge_meta[(src, dst)] = dependency
        if dst not in self.packages:
            self.packages[dst] = Package(name=dependency.name, source="inferred")
            self.edges.setdefault(dst, set())
            self.reverse_edges.setdefault(dst, set())

    def neighbors(self, name: str) -> Set[str]:
        return self.edges.get(normalize_name(name), set())

    def package_names(self) -> List[str]:
        return sorted(self.packages.keys())

    def to_adjacency(self) -> Dict[str, List[str]]:
        return {k: sorted(v) for k, v in sorted(self.edges.items())}