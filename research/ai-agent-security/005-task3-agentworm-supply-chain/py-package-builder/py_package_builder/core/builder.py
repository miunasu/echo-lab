"""Build wheel (and optional sdist) distributions for a package project."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .config import PackageConfig, load_config


class PackageBuilder:
    """Build bdist_wheel for a generated or existing package project."""

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
            if candidate.exists():
                self.config = load_config(candidate)
            else:
                self.config = None

    def ensure_build_backend(self) -> None:
        """Ensure setuptools and wheel are importable; install if missing."""
        missing = []
        for mod in ("setuptools", "wheel", "build"):
            try:
                __import__(mod)
            except ModuleNotFoundError:
                missing.append(mod if mod != "build" else "build")
        if missing:
            cmd = [sys.executable, "-m", "pip", "install", "--quiet", *missing]
            subprocess.run(cmd, check=True)

    def build(
        self,
        out_dir: Optional[str | Path] = None,
        sdist: bool = False,
        clean: bool = True,
    ) -> Dict[str, object]:
        """
        Build wheel into out_dir (default: <project>/dist).

        Returns dict: success, artifacts, stdout, stderr, returncode.
        """
        if not self.project_dir.exists():
            raise FileNotFoundError(f"Project directory not found: {self.project_dir}")

        pyproject = self.project_dir / "pyproject.toml"
        setup_py = self.project_dir / "setup.py"
        if not pyproject.exists() and not setup_py.exists():
            raise FileNotFoundError(
                f"No pyproject.toml or setup.py in {self.project_dir}. Run 'init' first."
            )

        out = Path(out_dir).resolve() if out_dir else self.project_dir / "dist"
        out.mkdir(parents=True, exist_ok=True)

        if clean:
            self._clean_build_artifacts()

        self.ensure_build_backend()

        # Prefer python -m build (PEP 517)
        artifacts: List[str] = []
        try:
            result = self._build_with_build_module(out, sdist=sdist)
        except Exception as exc:  # fallback
            result = self._build_with_setuptools(out, sdist=sdist, extra_note=str(exc))

        # Collect artifacts
        for path in sorted(out.glob("*")):
            if path.is_file() and path.suffix in {".whl", ".gz", ".zip"}:
                artifacts.append(str(path))

        result["artifacts"] = artifacts
        result["out_dir"] = str(out)
        result["success"] = result.get("returncode", 1) == 0 and bool(artifacts)
        return result

    def _clean_build_artifacts(self) -> None:
        for name in ("build", f"{self.config.import_name()}.egg-info" if self.config else None):
            if not name:
                continue
            path = self.project_dir / name
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
        # egg-info variants
        for path in self.project_dir.glob("*.egg-info"):
            shutil.rmtree(path, ignore_errors=True)

    def _build_with_build_module(self, out: Path, sdist: bool) -> Dict[str, object]:
        cmd = [
            sys.executable,
            "-m",
            "build",
            "--outdir",
            str(out),
            str(self.project_dir),
        ]
        if not sdist:
            cmd.insert(3, "--wheel")
        else:
            # both wheel + sdist by default when sdist=True; still ensure wheel
            pass
        if sdist:
            # build both
            cmd = [
                sys.executable,
                "-m",
                "build",
                "--outdir",
                str(out),
                str(self.project_dir),
            ]
        proc = subprocess.run(
            cmd,
            cwd=str(self.project_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return {
            "method": "build",
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "command": cmd,
        }

    def _build_with_setuptools(
        self,
        out: Path,
        sdist: bool,
        extra_note: str = "",
    ) -> Dict[str, object]:
        cmd = [
            sys.executable,
            "setup.py",
            "bdist_wheel",
            "--dist-dir",
            str(out),
        ]
        if sdist:
            cmd = [
                sys.executable,
                "setup.py",
                "sdist",
                "bdist_wheel",
                "--dist-dir",
                str(out),
            ]
        # If only pyproject exists, generate a minimal setup.py temporarily is risky;
        # use pip wheel instead.
        setup_py = self.project_dir / "setup.py"
        if not setup_py.exists():
            cmd = [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "-w",
                str(out),
                str(self.project_dir),
            ]
        proc = subprocess.run(
            cmd,
            cwd=str(self.project_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return {
            "method": "setuptools/pip",
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": (proc.stderr or "") + (f"\n[fallback note] {extra_note}" if extra_note else ""),
            "command": cmd,
        }