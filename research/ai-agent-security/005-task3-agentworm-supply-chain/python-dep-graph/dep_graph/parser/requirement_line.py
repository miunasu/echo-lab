"""Shared requirement line parsing utilities (PEP 508 subset)."""

from __future__ import annotations

import re
from typing import Optional, Tuple

from ..models import Dependency

_REQ_RE = re.compile(
    r"^\s*"
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"(?:\[(?P<extras>[^\]]*)\])?"
    r"\s*(?P<spec>(?:===|==|!=|<=|>=|~=|<|>)[^;]*)?"
    r"(?:\s*;\s*(?P<markers>.+))?"
    r"\s*$"
)

_URL_RE = re.compile(
    r"^\s*"
    r"(?:(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*@\s*)?"
    r"(?P<url>(?:https?|git\+https?|ssh|file)://\S+|"
    r"[A-Za-z0-9._/-]+\.git(?:@\S+)?)"
    r"(?:\s*;\s*(?P<markers>.+))?"
    r"\s*$"
)

_EDITABLE_RE = re.compile(
    r"^\s*(?:-e|--editable)\s+(?P<body>.+)$", re.IGNORECASE
)

_REQ_FILE_RE = re.compile(
    r"^\s*(?:-r|--requirement)\s+(?P<path>\S+)\s*$", re.IGNORECASE
)

_CONSTRAINT_RE = re.compile(
    r"^\s*(?:-c|--constraint)\s+(?P<path>\S+)\s*$", re.IGNORECASE
)


def strip_comment(line: str) -> str:
    """Remove unescaped trailing comments."""
    in_quote = None
    for i, ch in enumerate(line):
        if ch in ("'", '"'):
            if in_quote is None:
                in_quote = ch
            elif in_quote == ch:
                in_quote = None
        elif ch == "#" and in_quote is None:
            return line[:i].rstrip()
    return line.rstrip()


def parse_requirement_line(
    line: str, source: str = "", optional: bool = False
) -> Optional[Dependency]:
    """Parse a single requirement line into a Dependency."""
    raw = strip_comment(line).strip()
    if not raw:
        return None
    if raw.startswith("-") and not raw.lower().startswith(("-e", "--editable")):
        m_req = _REQ_FILE_RE.match(raw)
        if m_req:
            raise ValueError("INCLUDE_REQ:" + m_req.group("path"))
        m_c = _CONSTRAINT_RE.match(raw)
        if m_c:
            raise ValueError("INCLUDE_CONSTRAINT:" + m_c.group("path"))
        return None

    m_edit = _EDITABLE_RE.match(raw)
    if m_edit:
        body = m_edit.group("body").strip()
        egg = None
        if "#egg=" in body:
            body, frag = body.split("#egg=", 1)
            egg = frag.split("&")[0].strip()
        name = egg or body.rstrip("/").split("/")[-1].split("@")[0]
        return Dependency(
            name=name,
            version_spec="",
            source=source or "editable",
            optional=optional,
        )

    m_url = _URL_RE.match(raw)
    if m_url:
        name = m_url.group("name")
        url = m_url.group("url")
        if not name:
            name = url.rstrip("/").split("/")[-1]
            if name.endswith(".git"):
                name = name[:-4]
        return Dependency(
            name=name,
            version_spec="@ " + url,
            markers=(m_url.group("markers") or "").strip(),
            source=source or "url",
            optional=optional,
        )

    m = _REQ_RE.match(raw)
    if not m:
        token = raw.split()[0]
        if re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", token):
            return Dependency(name=token, source=source, optional=optional)
        return None

    extras_raw = m.group("extras") or ""
    extras = tuple(e.strip() for e in extras_raw.split(",") if e.strip())
    spec = (m.group("spec") or "").strip()
    markers = (m.group("markers") or "").strip()
    return Dependency(
        name=m.group("name"),
        version_spec=spec,
        extras=extras,
        markers=markers,
        source=source,
        optional=optional,
    )


def split_name_and_spec(value: str) -> Tuple[str, str]:
    """Split 'requests>=2.0' style strings used in setup.py lists."""
    value = value.strip().strip("'\"")
    m = _REQ_RE.match(value)
    if m:
        return m.group("name"), (m.group("spec") or "").strip()
    return value, ""