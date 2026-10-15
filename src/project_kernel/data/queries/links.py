"""Typed link extraction and the project.trace graph walker.

There is no ``object_link`` table in the P01 DDL (see handoff ChangeRequest), so
the trace graph is derived from the immutable ledger itself:

* ``revision.parent_ref``            -> relation ``parent``
* ObjectRef-shaped values anywhere inside a revision payload -> relation named
  by the payload field (for example ``requirement_refs``), so a reference typed
  as ``requirement/req-1`` and one typed as ``design/req-1`` stay distinct nodes.
* ``audit_event.causal_refs``        -> relation ``causal``

Nodes are keyed by ``project/type/id@revision`` so same-name-different-type
objects never collapse. The walk reports ``truncated`` when ``max_depth`` cut it
off instead of silently returning a partial graph.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator

from ...contracts.errors import KernelError, reference_not_found

_REF_KEYS = frozenset({"project_id", "object_type", "object_id", "revision_id"})
_MAX_SCAN = 20000


def is_object_ref(value: Any) -> bool:
    return (isinstance(value, dict) and _REF_KEYS.issubset(value.keys())
            and all(isinstance(value[k], str) for k in _REF_KEYS))


def node_id(ref: dict[str, Any]) -> str:
    return f"{ref['project_id']}/{ref['object_type']}/{ref['object_id']}@{ref['revision_id']}"


def _relation_name(path: str) -> str:
    last = path.split(".")[-1]
    return last.split("[")[0] or "ref"


def iter_refs(value: Any, path: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    if is_object_ref(value):
        yield path, value
        return
    if isinstance(value, dict):
        for key, child in value.items():
            yield from iter_refs(child, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_refs(child, f"{path}[{index}]")


@dataclass
class Edge:
    source: str
    target: str
    relation: str
    path: str = ""

    def key(self) -> tuple[str, str, str]:
        return (self.source, self.target, self.relation)


@dataclass
class TraceGraph:
    edges: list[Edge] = field(default_factory=list)
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    truncated_scan: bool = False


def _add_node(graph: TraceGraph, ref: dict[str, Any], *, exists: bool) -> str:
    nid = node_id(ref)
    if nid not in graph.nodes:
        graph.nodes[nid] = {"node_id": nid, "project_id": ref["project_id"],
                            "object_type": ref["object_type"], "object_id": ref["object_id"],
                            "revision_id": ref["revision_id"], "exists": exists,
                            "depth": None, "reached": None}
    elif exists:
        graph.nodes[nid]["exists"] = True
    return nid


def build_graph(conn: sqlite3.Connection, project_id: str, as_of_seq: int) -> TraceGraph:
    graph = TraceGraph()
    rows = conn.execute(
        "SELECT type, object_id, revision_id, payload_json, parent_ref FROM revision"
        " WHERE project_id=? AND commit_seq<=? ORDER BY commit_seq, ordinal",
        (project_id, as_of_seq)).fetchall()
    if len(rows) > _MAX_SCAN:
        graph.truncated_scan = True
        rows = rows[:_MAX_SCAN]
    seen: set[tuple[str, str, str]] = set()
    for object_type, object_id, revision_id, payload_json, parent_ref in rows:
        source_ref = {"project_id": project_id, "object_type": object_type,
                      "object_id": object_id, "revision_id": revision_id}
        source = _add_node(graph, source_ref, exists=True)
        if parent_ref:
            try:
                parent = json.loads(parent_ref)
            except (TypeError, ValueError):
                parent = None
            if is_object_ref(parent):
                target = _add_node(graph, parent, exists=False)
                edge = Edge(source, target, "parent", "parent_ref")
                if edge.key() not in seen:
                    seen.add(edge.key())
                    graph.edges.append(edge)
        try:
            payload = json.loads(payload_json) if payload_json else None
        except (TypeError, ValueError):
            payload = None
        if payload is not None:
            for path, ref in iter_refs(payload):
                target = _add_node(graph, ref, exists=False)
                edge = Edge(source, target, _relation_name(path), path)
                if edge.key() not in seen:
                    seen.add(edge.key())
                    graph.edges.append(edge)
    # causal refs recorded on audit events
    for causal_json, refs_json in conn.execute(
            "SELECT causal_refs, object_refs FROM audit_event WHERE commit_seq<=?"
            " AND (causal_refs IS NOT NULL OR object_refs IS NOT NULL)",
            (as_of_seq,)).fetchall():
        sources: list[dict[str, Any]] = []
        if refs_json:
            try:
                parsed = json.loads(refs_json)
            except (TypeError, ValueError):
                parsed = []
            for item in parsed if isinstance(parsed, list) else []:
                if is_object_ref(item):
                    sources.append(item)
        causals: list[dict[str, Any]] = []
        if causal_json:
            try:
                parsed_c = json.loads(causal_json)
            except (TypeError, ValueError):
                parsed_c = []
            for item in parsed_c if isinstance(parsed_c, list) else []:
                if is_object_ref(item):
                    causals.append(item)
        for source_ref in sources:
            source = _add_node(graph, source_ref, exists=False)
            for target_ref in causals:
                target = _add_node(graph, target_ref, exists=False)
                edge = Edge(source, target, "causal", "causal_refs")
                if edge.key() not in seen:
                    seen.add(edge.key())
                    graph.edges.append(edge)
    return graph


def _adjacency(graph: TraceGraph, direction: str) -> dict[str, list[Edge]]:
    adjacency: dict[str, list[Edge]] = {}
    for edge in graph.edges:
        if direction in ("outgoing", "both"):
            adjacency.setdefault(edge.source, []).append(edge)
        if direction in ("incoming", "both") and edge.source != edge.target:
            reverse = Edge(edge.target, edge.source, edge.relation, edge.path)
            adjacency.setdefault(reverse.source, []).append(reverse)
    return adjacency


def walk(graph: TraceGraph, root_ref: dict[str, Any], *, direction: str,
         max_depth: int) -> dict[str, Any]:
    root = node_id(root_ref)
    if root not in graph.nodes:
        raise KernelError(reference_not_found(f"{node_id(root_ref)} not found at as_of"))
    if direction not in ("incoming", "outgoing", "both"):
        raise KernelError(reference_not_found(f"unknown trace direction {direction!r}"))
    adjacency = _adjacency(graph, direction)
    graph.nodes[root]["depth"] = 0
    graph.nodes[root]["reached"] = direction
    reached: list[dict[str, Any]] = []
    used: set[tuple[str, str, str]] = set()
    frontier = [root]
    depth = 0
    truncated = graph.truncated_scan
    while frontier:
        if depth >= max_depth:
            if any(adjacency.get(nid) for nid in frontier):
                truncated = True
            break
        depth += 1
        next_frontier: list[str] = []
        for nid in frontier:
            for edge in sorted(adjacency.get(nid, []), key=lambda e: (e.relation, e.target)):
                key = (edge.source, edge.target, edge.relation)
                if key in used:
                    continue
                used.add(key)
                node = graph.nodes.get(edge.target)
                if node is None:
                    continue
                if node["depth"] is None:
                    node["depth"] = depth
                    node["reached"] = edge.relation
                    next_frontier.append(edge.target)
                    reached.append({"node_id": edge.target, "object_type": node["object_type"],
                                    "object_id": node["object_id"],
                                    "revision_id": node["revision_id"],
                                    "exists": node["exists"], "relation": edge.relation,
                                    "depth": depth})
        frontier = next_frontier
    edges_out = sorted(
        ({"from": e.source, "to": e.target, "relation": e.relation, "path": e.path}
         for e in graph.edges if (e.source, e.target, e.relation) in used),
        key=lambda e: (e["from"], e["relation"], e["to"]))
    return {"root": {"node_id": root, "object_type": root_ref["object_type"],
                     "object_id": root_ref["object_id"], "revision_id": root_ref["revision_id"]},
            "direction": direction, "max_depth": max_depth, "truncated": truncated,
            "nodes": reached, "edges": edges_out}
