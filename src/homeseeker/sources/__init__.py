"""Listing sources (portals)."""

from __future__ import annotations

from ..http import Http
from .base import Source
from .domiporta import DomiportaSource
from .morizon import MorizonSource
from .olx import OlxSource
from .otodom import OtodomSource

ALL_SOURCES: dict[str, type[Source]] = {
    OtodomSource.name: OtodomSource,
    OlxSource.name: OlxSource,
    MorizonSource.name: MorizonSource,  # also covers Gratka (same listings)
    DomiportaSource.name: DomiportaSource,
}


def build_sources(names: list[str] | None, http: Http) -> list[Source]:
    names = names or list(ALL_SOURCES)
    return [ALL_SOURCES[n](http) for n in names]
