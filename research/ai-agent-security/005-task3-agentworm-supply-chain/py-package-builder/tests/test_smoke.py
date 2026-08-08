"""Smoke tests for py-package-builder."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from py_package_builder.core.config import default_config, save_config, load_config, PackageConfig
from py_package_builder.core.generator import PackageGenerator
from py_package_builder.core.verifier import PackageVerifier
from py_package_builder.cli import main as cli_main


class ConfigTests(unittest.TestCase):
    def test_default_and_validate(self):
        cfg = default_config(name="hello_pkg", author="Tester")
        self.assertEqual(cfg.import_name(), "hello_pkg")
        self.assertEqual(cfg.validate(), [])

    def test_invalid_name(self):
        cfg = PackageConfig(name="1bad", author="x")
        errs = cfg.validate()
        self.assertTrue(any("name" in e.lower() for e in errs))

    def test_roundtrip_json(self):
        cfg = default_config(name="rt_pkg", version="1.2.3", author="A")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "cfg.json"
            save_config(cfg, path)
            loaded = load_config(path)
            self.assertEqual(loaded.name, "rt_pkg")
            self.assertEqual(loaded.version, "1.2.3")


class GeneratorVerifyTests(unittest.TestCase):
    def test_generate_and_verify(self):
        cfg = default_config(name="gen_demo", author="Spore")
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            result = PackageGenerator(cfg, td_path).generate(force=True)
            self.assertTrue(result["created"])
            self.assertTrue((td_path / "pyproject.toml").exists())
            self.assertTrue((td_path / "setup.py").exists())
            self.assertTrue((td_path / "gen_demo" / "__init__.py").exists())
            self.assertTrue((td_path / "gen_demo" / "core.py").exists())
            self.assertTrue((td_path / "gen_demo" / "cli.py").exists())

            save_config(cfg, td_path / "package.builder.json")
            report = PackageVerifier(td_path, config=cfg).verify()
            self.assertTrue(report.ok, report.to_dict())


class CliTests(unittest.TestCase):
    def test_cli_init_verify(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            code = cli_main(
                [
                    "init",
                    "-n",
                    "cli_demo",
                    "-a",
                    "Spore",
                    "-o",
                    str(td_path),
                    "--force",
                ]
            )
            self.assertEqual(code, 0)
            code = cli_main(["verify", "-p", str(td_path)])
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()