"""Base injector interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from adi.models import InjectionArtifact, InjectionFormat, PayloadResult, new_id


class BaseInjector(ABC):
    """Abstract base for format-specific ADI injectors."""

    format: InjectionFormat = InjectionFormat.RAW

    @abstractmethod
    def inject(
        self,
        payload: PayloadResult,
        *,
        field_path: str = "",
        base_document: Optional[Any] = None,
        **kwargs: Any,
    ) -> InjectionArtifact:
        """Embed *payload* into this format and return an artifact."""

    def _artifact(
        self,
        content: str,
        payload: PayloadResult,
        field_path: str = "",
        notes: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InjectionArtifact:
        return InjectionArtifact(
            artifact_id=new_id("artifact"),
            format=self.format,
            content=content,
            payload=payload,
            field_path=field_path,
            notes=notes,
            metadata=metadata or {},
        )