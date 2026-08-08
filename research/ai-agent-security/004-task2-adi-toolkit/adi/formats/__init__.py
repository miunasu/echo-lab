"""Multi-format ADI injectors (JSON / DOM / HTML / metadata)."""

from adi.formats.json_injector import JSONInjector
from adi.formats.dom_injector import DOMInjector
from adi.formats.html_injector import HTMLInjector
from adi.formats.metadata import MetadataInjector
from adi.formats.base import BaseInjector

__all__ = [
    "BaseInjector",
    "JSONInjector",
    "DOMInjector",
    "HTMLInjector",
    "MetadataInjector",
]