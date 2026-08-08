#!/usr/bin/env python
"""Setup script for py-package-builder."""

from setuptools import setup, find_packages

setup(
    name="py-package-builder",
    version="1.0.0",
    description="Automated Python package scaffolding and wheel builder",
    author="Spore",
    license="MIT",
    python_requires=">=3.8",
    packages=find_packages(include=["py_package_builder", "py_package_builder.*"]),
    install_requires=[],
    extras_require={
        "toml": ["tomli>=2.0; python_version < '3.11'", "tomli-w>=1.0"],
    },
    entry_points={
        "console_scripts": [
            "py-package-builder = py_package_builder.cli:main",
            "ppb = py_package_builder.cli:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)