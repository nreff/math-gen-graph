"""Local JSON cache for Wikidata enrichment data."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel

from .models import InstitutionEnrichment, PersonEnrichment

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".math-gen-graph"
CACHE_FILE = CACHE_DIR / "cache.json"
DEFAULT_TTL_DAYS = 30


class EnrichmentCache(BaseModel):
    """Persistent cache stored as JSON at ~/.math-gen-graph/cache.json."""

    version: int = 1
    people: dict[str, PersonEnrichment] = {}
    institutions: dict[str, InstitutionEnrichment] = {}

    # --- Lookup helpers with TTL check ---

    def get_person(
        self, name: str, ttl_days: int = DEFAULT_TTL_DAYS
    ) -> PersonEnrichment | None:
        """Return cached person enrichment if present and not expired."""
        entry = self.people.get(name)
        if entry and not _is_expired(entry.searched_at, ttl_days):
            return entry
        return None

    def get_institution(
        self, name: str, ttl_days: int = DEFAULT_TTL_DAYS
    ) -> InstitutionEnrichment | None:
        """Return cached institution enrichment if present and not expired."""
        entry = self.institutions.get(name)
        if entry and not _is_expired(entry.searched_at, ttl_days):
            return entry
        return None

    # --- Mutation helpers ---

    def put_person(self, name: str, enrichment: PersonEnrichment) -> None:
        self.people[name] = enrichment

    def put_institution(self, name: str, enrichment: InstitutionEnrichment) -> None:
        self.institutions[name] = enrichment

    # --- Persistence ---

    @classmethod
    def load(cls) -> EnrichmentCache:
        """Load the cache from disk, returning an empty cache if missing or corrupt."""
        if not CACHE_FILE.exists():
            return cls()
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            return cls.model_validate(data)
        except Exception as exc:
            logger.warning("Cache file corrupt, starting fresh: %s", exc)
            return cls()

    def save(self) -> None:
        """Write the cache to disk."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(
            self.model_dump_json(indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def clear() -> None:
        """Delete the cache file from disk."""
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
            logger.info("Cache cleared.")


def _is_expired(searched_at: datetime, ttl_days: int) -> bool:
    """Check whether a cache entry has exceeded its TTL."""
    now = datetime.now(timezone.utc)
    # Handle naive datetimes by assuming UTC
    if searched_at.tzinfo is None:
        searched_at = searched_at.replace(tzinfo=timezone.utc)
    return (now - searched_at) > timedelta(days=ttl_days)
