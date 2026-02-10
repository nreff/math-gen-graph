"""Async WebSocket client for fetching genealogy data from the geneagrapher backend."""

from __future__ import annotations

import json
import platform
import sys
from typing import Any, Callable

import websockets.client
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

from .models import Geneagraph, Record, StartNodeArg

GGRAPHER_URI = "wss://ggrphr.davidalber.net"
USER_AGENT = f"Python/{platform.python_version()} MathGenGraph/0.1.0"


def _intify_record_keys(d: dict[str, Any]) -> dict[Any, Any]:
    """Convert string keys in the 'nodes' dict to integers during JSON parsing."""
    if "nodes" in d:
        ret = {k: v for k, v in d.items() if k != "nodes"}
        ret["nodes"] = {int(k): v for k, v in d["nodes"].items()}
        return ret
    return d


def _build_payload(start_nodes: list[StartNodeArg], quiet: bool) -> dict:
    """Build the WebSocket request payload."""
    return {
        "kind": "build-graph",
        "options": {"reportingCallback": not quiet},
        "startNodes": [sn.to_request_dict() for sn in start_nodes],
    }


async def fetch_graph(
    start_nodes: list[StartNodeArg],
    quiet: bool = False,
) -> Geneagraph:
    """Connect to the geneagrapher backend and fetch the genealogy graph.

    Args:
        start_nodes: List of starting node arguments with traversal directions.
        quiet: If True, suppress progress display.

    Returns:
        A Geneagraph containing all fetched records.

    Raises:
        ConnectionError: If the backend is unavailable.
        RuntimeError: If the backend returns an unexpected response.
    """
    payload = _build_payload(start_nodes, quiet)

    progress = Progress(
        TextColumn("[bold blue]Fetching genealogy..."),
        BarColumn(bar_width=50),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        disable=quiet,
    )

    try:
        async with websockets.client.connect(
            GGRAPHER_URI,
            user_agent_header=USER_AGENT,
        ) as ws:
            await ws.send(json.dumps(payload))

            with progress:
                task_id = progress.add_task("Fetching", total=None)

                while True:
                    response_json = await ws.recv()
                    response = json.loads(
                        str(response_json),
                        object_hook=_intify_record_keys,
                    )
                    response_payload = response.get("payload")

                    if response["kind"] == "graph":
                        progress.update(task_id, completed=100, total=100)
                        # Parse into Pydantic models
                        nodes = {
                            int(k): Record(**v)
                            for k, v in response_payload["nodes"].items()
                        }
                        return Geneagraph(
                            start_nodes=response_payload["start_nodes"],
                            nodes=nodes,
                            status=response_payload["status"],
                        )
                    elif response["kind"] == "progress":
                        queued = response_payload["queued"]
                        fetching = response_payload["fetching"]
                        done = response_payload["done"]
                        total = queued + fetching + done
                        progress.update(task_id, completed=done, total=total)
                    else:
                        raise RuntimeError(
                            f"Unexpected response from backend: {response_json}"
                        )

    except websockets.exceptions.WebSocketException as exc:
        raise ConnectionError(
            "Geneagrapher backend is currently unavailable. "
            "Please try again later."
        ) from exc
