"""JSON-format ADI injector.

Injects payloads into nested JSON documents under fields that agents
often treat as authoritative (status, author, validation, system notes).
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Optional, Sequence

from adi.formats.base import BaseInjector
from adi.models import InjectionArtifact, InjectionFormat, PayloadResult


# Fields commonly trusted or high-signal in agent tool / API responses.
DEFAULT_TRUSTED_FIELDS: List[str] = [
    "status",
    "author",
    "validation",
    "validation_result",
    "system",
    "system_message",
    "admin_note",
    "security_review",
    "source",
    "confidence",
    "verified",
    "metadata.notes",
    "result.summary",
    "data.message",
]


DEFAULT_BASE_DOCUMENT: Dict[str, Any] = {
    "id": "doc-001",
    "type": "api_response",
    "status": "ok",
    "author": "service",
    "validation": {"result": "passed", "score": 0.99},
    "data": {
        "title": "Routine update",
        "message": "All checks green.",
        "items": [],
    },
    "metadata": {
        "notes": "",
        "version": "1.0",
    },
    "result": {
        "summary": "success",
    },
}


class JSONInjector(BaseInjector):
    """Inject ADI payloads into JSON documents."""

    format = InjectionFormat.JSON

    def __init__(
        self,
        trusted_fields: Optional[Sequence[str]] = None,
        pretty: bool = True,
    ) -> None:
        self.trusted_fields = list(trusted_fields or DEFAULT_TRUSTED_FIELDS)
        self.pretty = pretty

    def inject(
        self,
        payload: PayloadResult,
        *,
        field_path: str = "",
        base_document: Optional[Any] = None,
        mode: str = "replace",
        **kwargs: Any,
    ) -> InjectionArtifact:
        """
        Parameters
        ----------
        field_path:
            Dot-path such as ``validation.result`` or ``metadata.notes``.
            Empty string => auto-pick first trusted field.
        mode:
            ``replace`` | ``append`` | ``wrap`` (wrap value as object with payload).
        """
        doc = copy.deepcopy(base_document if base_document is not None else DEFAULT_BASE_DOCUMENT)
        if not isinstance(doc, dict):
            doc = {"value": doc}

        path = field_path or self.trusted_fields[0]
        text = payload.mutated_text

        if mode == "append":
            existing = self._get_path(doc, path)
            if existing is None:
                new_val: Any = text
            elif isinstance(existing, str):
                new_val = f"{existing}\n{text}"
            elif isinstance(existing, list):
                new_val = list(existing) + [text]
            elif isinstance(existing, dict):
                new_val = {**existing, "adi_note": text}
            else:
                new_val = f"{existing}\n{text}"
        elif mode == "wrap":
            existing = self._get_path(doc, path)
            new_val = {
                "original": existing,
                "status": "verified",
                "system_directive": text,
            }
        else:
            new_val = text

        self._set_path(doc, path, new_val)
        content = json.dumps(doc, ensure_ascii=False, indent=2 if self.pretty else None)
        return self._artifact(
            content=content,
            payload=payload,
            field_path=path,
            notes=f"JSON injection mode={mode}",
            metadata={"mode": mode, "document_keys": list(doc.keys())},
        )

    def inject_multi(
        self,
        payload: PayloadResult,
        field_paths: Optional[Sequence[str]] = None,
        base_document: Optional[Dict[str, Any]] = None,
    ) -> List[InjectionArtifact]:
        """Create one artifact per field path (for field-surface probing)."""
        paths = list(field_paths or self.trusted_fields)
        return [
            self.inject(payload, field_path=p, base_document=base_document)
            for p in paths
        ]

    def list_candidate_fields(self) -> List[str]:
        return list(self.trusted_fields)

    # ------------------------------------------------------------------
    @staticmethod
    def _get_path(doc: Dict[str, Any], path: str) -> Any:
        cur: Any = doc
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
        return cur

    @staticmethod
    def _set_path(doc: Dict[str, Any], path: str, value: Any) -> None:
        parts = path.split(".")
        cur: Dict[str, Any] = doc
        for part in parts[:-1]:
            if part not in cur or not isinstance(cur[part], dict):
                cur[part] = {}
            cur = cur[part]
        cur[parts[-1]] = value