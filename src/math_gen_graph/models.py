"""Pydantic data models for the math genealogy graph visualizer."""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, field_validator


class Record(BaseModel):
    """A single mathematician record from the Math Genealogy Project."""

    id: int
    name: str
    institution: str | None = None
    year: int | None = None
    descendants: list[int] = []
    advisors: list[int] = []


class Geneagraph(BaseModel):
    """The full genealogy graph returned by the backend."""

    start_nodes: list[int]
    nodes: dict[int, Record]
    status: Literal["complete", "truncated"]


class TraversalDirection(str, Enum):
    """Which direction to traverse the genealogy tree."""

    ADVISORS = "a"
    DESCENDANTS = "d"
    BOTH = "ad"


class StartNodeArg(BaseModel):
    """A parsed start node argument like '18231:a'."""

    record_id: int
    request_advisors: bool = False
    request_descendants: bool = False

    @classmethod
    def from_string(cls, val: str) -> StartNodeArg:
        """Parse a string like '18231:a', '18231:d', or '18231:ad'."""
        match = re.fullmatch(r"(\d+):(a|d|ad|da)", val)
        if match is None:
            raise ValueError(
                f"Invalid start node format: '{val}'. "
                "Expected format: ID:DIRECTION where DIRECTION is 'a', 'd', or 'ad'."
            )
        record_id = int(match.group(1))
        direction = match.group(2)
        return cls(
            record_id=record_id,
            request_advisors="a" in direction,
            request_descendants="d" in direction,
        )

    def to_request_dict(self) -> dict:
        """Convert to the dict format expected by the WebSocket API."""
        return {
            "recordId": self.record_id,
            "getAdvisors": self.request_advisors,
            "getDescendants": self.request_descendants,
        }


class OutputFormat(str, Enum):
    """Output format for the graph."""

    HTML = "html"
    PNG = "png"
    SVG = "svg"


class ThemeName(str, Enum):
    """Available theme names."""

    DARK = "dark"
    LIGHT = "light"
    ACADEMIC = "academic"


class ColorBy(str, Enum):
    """What attribute to color-code nodes by."""

    INSTITUTION = "institution"
    ERA = "era"
    DEPTH = "depth"


class LayoutEngine(str, Enum):
    """Graph layout algorithm."""

    HIERARCHICAL = "hierarchical"
    FORCE = "force"
    RADIAL = "radial"


class ThemeConfig(BaseModel):
    """Visual theme configuration for graph rendering."""

    name: str
    bg_color: str
    node_colors: list[str]
    edge_color: str
    edge_highlight_color: str
    font_family: str
    font_color: str
    font_size: int = 14
    highlight_color: str
    node_border_color: str
    node_border_width: int = 2
    node_shape: str = "box"


class RenderOptions(BaseModel):
    """All options needed to render a graph."""

    output_format: OutputFormat = OutputFormat.HTML
    theme_name: ThemeName = ThemeName.LIGHT
    color_by: ColorBy = ColorBy.INSTITUTION
    layout: LayoutEngine = LayoutEngine.HIERARCHICAL
    output_path: str = "output.html"


# --------------------------------------------------------------------------- #
# Enrichment models (Wikipedia links, institution flags via Wikidata)
# --------------------------------------------------------------------------- #


class PersonEnrichment(BaseModel):
    """Cached Wikidata enrichment for a person."""

    wikidata_id: str | None = None
    wikipedia_url: str | None = None
    searched_at: datetime


class InstitutionEnrichment(BaseModel):
    """Cached Wikidata enrichment for an institution."""

    wikidata_id: str | None = None
    country: str | None = None
    country_code: str | None = None
    flag_url: str | None = None
    flag_url_by_era: dict[str, str] = {}  # "1800-1900" -> commons thumb URL
    searched_at: datetime


class EnrichedData(BaseModel):
    """Enrichment data for an entire graph, keyed by name / institution."""

    people: dict[str, PersonEnrichment] = {}
    institutions: dict[str, InstitutionEnrichment] = {}

    def wikipedia_url_for(self, name: str) -> str | None:
        """Look up the Wikipedia URL for a person by name."""
        entry = self.people.get(name)
        return entry.wikipedia_url if entry else None

    def flag_url_for(self, institution: str, year: int | None = None) -> str | None:
        """Look up the flag URL for an institution, optionally at a specific year."""
        entry = self.institutions.get(institution)
        if not entry:
            return None
        if year and entry.flag_url_by_era:
            for era_range, url in entry.flag_url_by_era.items():
                parts = era_range.split("-")
                try:
                    start = int(parts[0]) if parts[0] else 0
                    end = int(parts[1]) if len(parts) > 1 and parts[1] else 9999
                    if start <= year <= end:
                        return url
                except ValueError:
                    continue
        return entry.flag_url

    def country_for(self, institution: str) -> str | None:
        """Look up the country name for an institution."""
        entry = self.institutions.get(institution)
        return entry.country if entry else None
