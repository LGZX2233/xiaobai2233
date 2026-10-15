"""P06-owned read-only query services (project data read models).

Exports the QueryService plus the watermark/envelope and trace helpers so P10
(offline RPC bridge) and P12 (workbench pages) can build QueryEnvelopes without
re-implementing watermark or pagination-token logic.
"""
from .links import build_graph, node_id, walk
from .service import QueryService
from .watermarks import (
    COMPLETE,
    INCOMPLETE,
    PROJECTION_VERSION,
    UNKNOWN,
    ReadEnvelope,
    decode_page_token,
    encode_page_token,
)

__all__ = [
    "QueryService",
    "ReadEnvelope",
    "encode_page_token",
    "decode_page_token",
    "build_graph",
    "walk",
    "node_id",
    "PROJECTION_VERSION",
    "COMPLETE",
    "INCOMPLETE",
    "UNKNOWN",
]
