"""Verify package project structure and built artifacts."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .config import PackageConfig, load_config


@dataclass
class CheckResult:
    name: str
    ok: bool
    message: str


@dataclass
class VerifyReport:
    ok: bool
    checks: List[CheckResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "ok": self.ok,
            "checks": [{"name": c.name, "ok": c.ok, "message": c.message} for c in self.checks],
            "errors": self.errors,
            "warnings": self.warnings,
        }


class PackageVerifier:
    """Validate scaffolded project layout and optional wheel contents."""

    REQUIRED_ROOT_FILES = ("pyproject.toml", "setup.py")  # at least one
    REQUIRED_DOCS = ("README.md",)

    def __init__(
        self,
        project_dir: str | Path,
        config: Optional[PackageConfig] = None,
        config_path: Optional[str | Path] = None,
    ):
        self.project_dir = Path(project_dir).resolve()
        if config is not None:
            self.config = config
        elif config_path:
            self.config = load_config(config_path)
        else:
            candidate = self.project_dir / "package.builder.toml"
            self.config = load_config(candidate) if candidate.exists() else None

    def verify(self, wheel_path: Optional[str | Path] = None) -> VerifyReport:
        report = VerifyReport(ok=True)
        self._check_project_root(report)
        self._check_package_layout(report)
        self._check_metadata_files(report)
        if wheel_path:
            self._check_wheel(Path(wheel_path), report)
        else:
            dist = self.project_dir / "dist"
            wheels = sorted(dist.glob("*.whl")) if dist.exists() else []
            if wheels:
                self._check_wheel(wheels[-1], report)
            else:
                report.checks.append(
                    CheckResult("wheel", True, "No wheel present (skipped artifact check)")
                )

        report.ok = all(c.ok for c in report.checks if c.name != "wheel_optional") and not report.errors
        # recompute strictly: any failed check => not ok
        report.ok = all(c.ok for c in report.checks) and not report.errors
        return report

    def _add(self, report: VerifyReport, name: str, ok: bool, message: str) -> None:
        report.checks.append(CheckResult(name, ok, message))
        if not ok:
            report.errors.append(f"{name}: {message}")

    def _check_project_root(self, report: VerifyReport) -> None:
        if not self.project_dir.is_dir():
            self._add(report, "project_dir", False, f"Not a directory: {self.project_dir}")
            return
        self._add(report, "project_dir", True, str(self.project_dir))

        has_meta = (self.project_dir / "pyproject.toml").exists() or (
            self.project_dir / "setup.py"
        ).exists()
        self._add(
            report,
            "build_metadata",
            has_meta,
            "pyproject.toml or setup.py found" if has_meta else "Missing pyproject.toml and setup.py",
        )

    def _check_package_layout(self, report: VerifyReport) -> None:
        import_name = (
            self.config.import_name()
            if self.config
            else self._guess_import_name()
        )
        if not import_name:
            self._add(report, "package_dir", False, "Cannot determine package import name")
            return

        pkg_dir = self.project_dir / import_name
        init_py = pkg_dir / "__init__.py"
        if not pkg_dir.is_dir():
            self._add(report, "package_dir", False, f"Missing package directory: {import_name}/")
            return
        self._add(report, "package_dir", True, f"{import_name}/ exists")

        self._add(
            report,
            "package_init",
            init_py.is_file(),
            f"{import_name}/__init__.py OK" if init_py.is_file() else "Missing __init__.py",
        )

        if self.config:
            for mod in self.config.modules:
                mod_path = pkg_dir / f"{mod.name}.py"
                self._add(
                    report,
                    f"module:{mod.name}",
                    mod_path.is_file(),
                    str(mod_path.relative_to(self.project_dir))
                    if mod_path.is_file()
                    else f"Missing module {mod.name}.py",
                )
            for ep in self.config.entry_points:
                # module path like pkg.cli -> pkg/cli.py
                parts = ep.module.split(".")
                if parts and parts[0] == import_name:
                    mod_file = self.project_dir.joinpath(*parts[:-1], parts[-1] + ".py") if len(parts) > 1 else None
                    # entry module file
                    rel_parts = parts[1:]
                    candidate = pkg_dir.joinpath(*rel_parts[:-1], rel_parts[-1] + ".py") if rel_parts else init_py
                    ok = candidate.is_file()
                    self._add(
                        report,
                        f"entry:{ep.name}",
                        ok,
                        f"{ep.module}:{ep.attr}" + ("" if ok else " (module file missing)"),
                    )

    def _check_metadata_files(self, report: VerifyReport) -> None:
        readme = self.project_dir / "README.md"
        self._add(
            report,
            "readme",
            readme.is_file(),
            "README.md present" if readme.is_file() else "README.md missing",
        )

        # Validate pyproject basics if present
        pyproject = self.project_dir / "pyproject.toml"
        if pyproject.is_file():
            text = pyproject.read_text(encoding="utf-8")
            has_name = re.search(r'name\s*=\s*".+"', text) is not None
            has_version = re.search(r'version\s*=\s*".+"', text) is not None
            self._add(
                report,
                "pyproject_fields",
                has_name and has_version,
                "name/version present" if (has_name and has_version) else "name or version missing in pyproject.toml",
            )

        if self.config:
            errs = self.config.validate()
            self._add(
                report,
                "config_validation",
                not errs,
                "config OK" if not errs else "; ".join(errs),
            )

    def _check_wheel(self, wheel_path: Path, report: VerifyReport) -> None:
        if not wheel_path.is_file():
            self._add(report, "wheel", False, f"Wheel not found: {wheel_path}")
            return
        if not zipfile.is_zipfile(wheel_path):
            self._add(report, "wheel", False, f"Not a valid zip/wheel: {wheel_path}")
            return

        with zipfile.ZipFile(wheel_path, "r") as zf:
            names = zf.namelist()
            has_dist_info = any(".dist-info/METADATA" in n or n.endswith(".dist-info/METADATA") for n in names)
            has_whl_record = any(n.endswith(".dist-info/RECORD") for n in names)
            import_name = self.config.import_name() if self.config else self._guess_import_name()
            has_pkg = any(
                n.startswith(import_name + "/") or n.startswith(import_name + "\\")
                for n in names
            ) if import_name else True

            self._add(report, "wheel_zip", True, f"{wheel_path.name} ({len(names)} files)")
            self._add(report, "wheel_dist_info", has_dist_info, "METADATA present" if has_dist_info else "METADATA missing")
            self._add(report, "wheel_record", has_whl_record, "RECORD present" if has_whl_record else "RECORD missing")
            self._add(
                report,
                "wheel_package",
                has_pkg,
                f"package '{import_name}' inside wheel" if has_pkg else f"package '{import_name}' not found in wheel",
            )

    def _guess_import_name(self) -> Optional[str]:
        # pick first directory with __init__.py that is not tests
        for child in sorted(self.project_dir.iterdir()):
            if child.is_dir() and child.name not in {"tests", "test", "dist", "build", ".git"}:
                if (child / "__init__.py").exists():
                    return child.name
        return None