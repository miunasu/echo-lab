"""Export asset inventory to JSON / CSV."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Union


def export_json(assets: List[Dict[str, Any]], output_path: Union[str, Path], pretty: bool = True) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        if pretty:
            json.dump(assets, f, ensure_ascii=False, indent=2)
            f.write("\n")
        else:
            json.dump(assets, f, ensure_ascii=False, separators=(",", ":"))
    return str(path.resolve())


def export_csv(assets: List[Dict[str, Any]], output_path: Union[str, Path]) -> str:
    """
    Flatten assets to CSV rows:
    ip, port, service, version, os, banner
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["ip", "port", "service", "version", "os", "banner"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for asset in assets:
            ip = asset.get("ip", "")
            os_name = asset.get("os", "")
            ports = asset.get("ports") or []
            if not ports:
                writer.writerow(
                    {
                        "ip": ip,
                        "port": "",
                        "service": "",
                        "version": "",
                        "os": os_name,
                        "banner": "",
                    }
                )
                continue
            for p in ports:
                writer.writerow(
                    {
                        "ip": ip,
                        "port": p.get("port", ""),
                        "service": p.get("service", ""),
                        "version": p.get("version", "") or "",
                        "os": os_name,
                        "banner": p.get("banner", "") or "",
                    }
                )
    return str(path.resolve())


def export_assets(
    assets: List[Dict[str, Any]],
    output_path: Union[str, Path],
    fmt: str = "auto",
) -> str:
    """
    Export by format. fmt: json | csv | auto (by suffix).
    """
    path = Path(output_path)
    format_name = fmt.lower()
    if format_name == "auto":
        suffix = path.suffix.lower()
        if suffix == ".csv":
            format_name = "csv"
        else:
            format_name = "json"

    if format_name == "csv":
        return export_csv(assets, path)
    if format_name == "json":
        return export_json(assets, path)
    raise ValueError(f"Unsupported format: {fmt}")