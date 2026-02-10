"""Wikidata enrichment: Wikipedia links for people, country flags for institutions."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import datetime, timezone

import httpx

from .cache import EnrichmentCache
from .models import (
    EnrichedData,
    Geneagraph,
    InstitutionEnrichment,
    PersonEnrichment,
)

logger = logging.getLogger(__name__)

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
USER_AGENT = "MathGenGraph/0.1.0 (https://github.com/math-gen-graph) Python/httpx"

# Wikidata asks unregistered users to keep requests to ~1/sec
RATE_LIMIT_SECONDS = 1.2

# Maximum names per SPARQL VALUES clause (keep queries reasonable)
BATCH_SIZE = 50


def _split_compound_institution(name: str) -> list[str]:
    """Split compound institution names like 'Uni A and Uni B' into parts."""
    # The MGP often uses " and " to join multiple institutions
    parts = re.split(r"\s+and\s+", name)
    return [p.strip() for p in parts if p.strip()]


def _commons_thumb_url(filename: str, width: int = 40) -> str:
    """Convert a Wikimedia Commons filename to a thumbnail URL.

    Commons thumbnail URLs follow a hash-based directory scheme:
    https://upload.wikimedia.org/wikipedia/commons/thumb/HASH/filename/WIDTHpx-filename

    For SVG files, Wikimedia serves PNG thumbnails at .../WIDTHpx-filename.png
    """
    # The filename from SPARQL comes as a full URL like:
    # http://commons.wikimedia.org/wiki/Special:FilePath/Flag_of_Germany.svg
    if "Special:FilePath/" in filename:
        filename = filename.split("Special:FilePath/")[-1]
    # URL-decode %20 etc.
    filename = filename.replace("%20", " ")
    # Compute MD5 hash for the directory structure
    md5 = hashlib.md5(filename.encode("utf-8")).hexdigest()
    a, b = md5[0], md5[:2]
    encoded = filename.replace(" ", "_")
    thumb = (
        f"https://upload.wikimedia.org/wikipedia/commons/thumb/"
        f"{a}/{b}/{encoded}/{width}px-{encoded}"
    )
    # SVG files are served as PNG thumbnails by Wikimedia
    if encoded.lower().endswith(".svg"):
        thumb += ".png"
    return thumb


def _escape_sparql_string(s: str) -> str:
    """Escape a string for inclusion in a SPARQL literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


async def _sparql_query(client: httpx.AsyncClient, query: str) -> list[dict]:
    """Execute a SPARQL query against Wikidata and return the bindings.

    Uses POST to avoid URL length limits with large batch queries.
    """
    try:
        resp = await client.post(
            WIKIDATA_SPARQL_URL,
            data={"query": query},
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/sparql-results+json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", {}).get("bindings", [])
    except Exception as exc:
        logger.warning("SPARQL query failed: %s", exc)
        return []


async def _batch_lookup_people(
    client: httpx.AsyncClient,
    names: list[str],
) -> dict[str, PersonEnrichment]:
    """Batch-query Wikidata for Wikipedia URLs of people by name."""
    results: dict[str, PersonEnrichment] = {}
    now = datetime.now(timezone.utc)

    for i in range(0, len(names), BATCH_SIZE):
        batch = names[i : i + BATCH_SIZE]
        values = " ".join(
            f'"{_escape_sparql_string(n)}"@en' for n in batch
        )
        query = f"""
        SELECT ?name ?item ?article WHERE {{
          VALUES ?name {{ {values} }}
          ?item rdfs:label ?name .
          ?item wdt:P31 wd:Q5 .
          ?article schema:about ?item ;
                   schema:isPartOf <https://en.wikipedia.org/> .
        }}
        """
        bindings = await _sparql_query(client, query)

        for b in bindings:
            name = b.get("name", {}).get("value", "")
            wikidata_id = b.get("item", {}).get("value", "").split("/")[-1]
            article_url = b.get("article", {}).get("value", "")
            if name and article_url:
                results[name] = PersonEnrichment(
                    wikidata_id=wikidata_id,
                    wikipedia_url=article_url,
                    searched_at=now,
                )

        if i + BATCH_SIZE < len(names):
            await asyncio.sleep(RATE_LIMIT_SECONDS)

    # Mark names with no result so we don't re-query them
    for name in names:
        if name not in results:
            results[name] = PersonEnrichment(searched_at=now)

    return results


async def _batch_lookup_institutions(
    client: httpx.AsyncClient,
    institution_names: list[str],
) -> dict[str, InstitutionEnrichment]:
    """Batch-query Wikidata for institution country + flag.

    Handles compound institution names (e.g. "Uni A and Uni B") by splitting them
    and querying individual parts, then mapping results back to the original names.
    """
    results: dict[str, InstitutionEnrichment] = {}
    now = datetime.now(timezone.utc)

    # Split compound names and track which originals they map to
    # individual_name -> list of original compound names that contain it
    individual_to_originals: dict[str, list[str]] = {}
    unique_individuals: list[str] = []

    for orig_name in institution_names:
        parts = _split_compound_institution(orig_name)
        for part in parts:
            if part not in individual_to_originals:
                individual_to_originals[part] = []
                unique_individuals.append(part)
            individual_to_originals[part].append(orig_name)

    # Query Wikidata for individual institution names
    individual_results: dict[str, InstitutionEnrichment] = {}

    # Search across multiple languages since MGP uses native institution names
    # (German, French, Italian, Latin, Dutch, etc.)
    languages = ["en", "de", "fr", "it", "la", "nl", "es", "pt", "pl", "cs"]

    for i in range(0, len(unique_individuals), BATCH_SIZE):
        batch = unique_individuals[i : i + BATCH_SIZE]
        # Build VALUES with all language variants for each name
        value_entries = []
        for n in batch:
            escaped = _escape_sparql_string(n)
            for lang in languages:
                value_entries.append(f'"{escaped}"@{lang}')
        values = " ".join(value_entries)

        query = f"""
        SELECT ?searchLabel ?inst ?country ?countryLabel ?countryCode ?flagImage WHERE {{
          VALUES ?searchLabel {{ {values} }}
          ?inst rdfs:label ?searchLabel .
          ?inst wdt:P17 ?country .
          OPTIONAL {{ ?country wdt:P297 ?countryCode . }}
          OPTIONAL {{ ?country wdt:P41 ?flagImage . }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
        }}
        """
        bindings = await _sparql_query(client, query)

        for b in bindings:
            search_label = b.get("searchLabel", {}).get("value", "")
            if not search_label:
                continue
            # Map the matched label back to the original name
            # (the label might be in any language but the text matches our input)
            if search_label not in individual_to_originals and search_label not in [
                n for n in unique_individuals
            ]:
                continue
            if search_label in individual_results:
                continue

            wikidata_id = b.get("inst", {}).get("value", "").split("/")[-1]
            country = b.get("countryLabel", {}).get("value", "")
            country_code = b.get("countryCode", {}).get("value", "")
            flag_raw = b.get("flagImage", {}).get("value", "")
            flag_url = _commons_thumb_url(flag_raw) if flag_raw else None

            individual_results[search_label] = InstitutionEnrichment(
                wikidata_id=wikidata_id,
                country=country or None,
                country_code=country_code.lower() if country_code else None,
                flag_url=flag_url,
                searched_at=now,
            )

        if i + BATCH_SIZE < len(unique_individuals):
            await asyncio.sleep(RATE_LIMIT_SECONDS)

    # Collect unique country URIs for historical flag lookup
    country_uris: dict[str, str] = {}  # country_label -> country URI

    # Get country URIs from the institutions we found
    found_names = [n for n in unique_individuals if n in individual_results and individual_results[n].country]
    for i in range(0, len(found_names), BATCH_SIZE):
        batch = found_names[i : i + BATCH_SIZE]
        # Multi-language search for country URIs too
        value_entries = []
        for n in batch:
            escaped = _escape_sparql_string(n)
            for lang in languages:
                value_entries.append(f'"{escaped}"@{lang}')
        values = " ".join(value_entries)
        query = f"""
        SELECT DISTINCT ?countryLabel ?country WHERE {{
          VALUES ?instName {{ {values} }}
          ?inst rdfs:label ?instName .
          ?inst wdt:P17 ?country .
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
        }}
        """
        bindings = await _sparql_query(client, query)
        for b in bindings:
            c_label = b.get("countryLabel", {}).get("value", "")
            c_uri = b.get("country", {}).get("value", "")
            if c_label and c_uri:
                country_uris[c_label] = c_uri

        await asyncio.sleep(RATE_LIMIT_SECONDS)

    # Fetch historical flags for each country
    historical_flags: dict[str, list[dict]] = {}
    for country_label, country_uri in country_uris.items():
        qid = country_uri.split("/")[-1]
        query = f"""
        SELECT ?flagImage ?startDate ?endDate WHERE {{
          wd:{qid} p:P41 ?flagStmt .
          ?flagStmt ps:P41 ?flagImage .
          OPTIONAL {{ ?flagStmt pq:P580 ?startDate . }}
          OPTIONAL {{ ?flagStmt pq:P582 ?endDate . }}
        }}
        """
        bindings = await _sparql_query(client, query)
        flags = []
        for b in bindings:
            flag_raw = b.get("flagImage", {}).get("value", "")
            start_str = b.get("startDate", {}).get("value", "")
            end_str = b.get("endDate", {}).get("value", "")
            start_year = _parse_year(start_str)
            end_year = _parse_year(end_str)
            if flag_raw:
                flags.append({
                    "flag_url": _commons_thumb_url(flag_raw),
                    "start": start_year,
                    "end": end_year,
                })
        if flags:
            historical_flags[country_label] = flags

        await asyncio.sleep(RATE_LIMIT_SECONDS)

    # Merge historical flags into individual results
    for inst_name, inst in individual_results.items():
        if inst.country and inst.country in historical_flags:
            era_map: dict[str, str] = {}
            for f in historical_flags[inst.country]:
                start = f["start"] or 0
                end = f["end"] or 9999
                era_key = f"{start}-{end}"
                era_map[era_key] = f["flag_url"]
            inst.flag_url_by_era = era_map

    # Map individual results back to original (possibly compound) names
    for orig_name in institution_names:
        if orig_name in individual_results:
            # Direct match
            results[orig_name] = individual_results[orig_name]
        else:
            # Check parts of the compound name -- use the first part that matched
            parts = _split_compound_institution(orig_name)
            matched = False
            for part in parts:
                if part in individual_results:
                    results[orig_name] = individual_results[part].model_copy()
                    results[orig_name].searched_at = now
                    matched = True
                    break
            if not matched:
                results[orig_name] = InstitutionEnrichment(searched_at=now)

    return results


def _parse_year(date_str: str) -> int | None:
    """Extract a year from an ISO date string like '1933-03-14T00:00:00Z'."""
    if not date_str:
        return None
    match = re.match(r"(\d{4})", date_str)
    return int(match.group(1)) if match else None


async def enrich_graph(
    geneagraph: Geneagraph,
    cache: EnrichmentCache | None = None,
) -> EnrichedData:
    """Enrich a Geneagraph with Wikipedia links and institution flags.

    Uses the cache for known entries and queries Wikidata for misses.
    Updates the cache in place and saves it to disk.
    """
    if cache is None:
        cache = EnrichmentCache.load()

    # Collect unique names and institutions
    all_names: set[str] = set()
    all_institutions: set[str] = set()
    for record in geneagraph.nodes.values():
        all_names.add(record.name)
        if record.institution:
            all_institutions.add(record.institution)

    # Partition into cached vs uncached
    uncached_names = [n for n in all_names if cache.get_person(n) is None]
    uncached_institutions = [
        i for i in all_institutions if cache.get_institution(i) is None
    ]

    logger.info(
        "Enrichment: %d/%d people cached, %d/%d institutions cached",
        len(all_names) - len(uncached_names),
        len(all_names),
        len(all_institutions) - len(uncached_institutions),
        len(all_institutions),
    )

    # Query Wikidata for cache misses
    if uncached_names or uncached_institutions:
        async with httpx.AsyncClient() as client:
            if uncached_names:
                logger.info("Querying Wikidata for %d people...", len(uncached_names))
                new_people = await _batch_lookup_people(client, uncached_names)
                for name, enrichment in new_people.items():
                    cache.put_person(name, enrichment)

            if uncached_institutions:
                logger.info(
                    "Querying Wikidata for %d institutions...",
                    len(uncached_institutions),
                )
                new_institutions = await _batch_lookup_institutions(
                    client, uncached_institutions
                )
                for name, enrichment in new_institutions.items():
                    cache.put_institution(name, enrichment)

        # Save updated cache
        cache.save()

    # Build enriched data from cache
    people = {n: cache.people[n] for n in all_names if n in cache.people}
    institutions = {
        i: cache.institutions[i] for i in all_institutions if i in cache.institutions
    }

    return EnrichedData(people=people, institutions=institutions)
