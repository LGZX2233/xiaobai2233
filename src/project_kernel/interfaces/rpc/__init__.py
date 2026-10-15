"""P10-owned JSON-RPC interface package.

Public surface: strict stdio framing, the typed protocol server, trusted
invocation-context handles, the machine command surface policy, session guards
(in-flight limit, receipt replay) and the ``source.ingest`` envelope mapping.
"""

from .commands import (  # noqa: F401
    IDENTITY_RECEIPT_DOMAIN_COMMANDS,
    SELECTOR_ID_KEYS,
    canonical_selector,
    compute_input_hash,
    receipt_domain_for,
)
from .framing import (  # noqa: F401
    MAX_FRAME_BYTES_DEFAULT,
    MIN_FRAME_BYTES,
    FrameError,
    FrameTooLarge,
    LineFramer,
    decode_frame,
    encode_frame,
    parse_json_strict,
)
from .ingest import (  # noqa: F401
    SOURCE_INGEST_COMMAND,
    ObservedRange,
    SourceEvent,
    SourceIngestBridge,
    SourceIngestRequest,
    SourceStreamKey,
    map_source_ingest,
)
from .invocation import (  # noqa: F401
    CURRENT_MACHINE_CONTEXT,
    INVOCATION_CONTEXT_FIELD,
    InteractionProof,
    InvocationContextRegistry,
    MachineContext,
    coerce_machine_context,
    current_machine_context,
    resolve_context,
    sanitize_for_log,
    strip_invocation_context,
)
from .policy import (  # noqa: F401
    HUMAN_ONLY_COMMANDS,
    CommandSurface,
    ProtocolSurfaceError,
    build_surface,
)
from .protocol import Limits, ProtocolServer, current_machine_context  # noqa: F401
from .session import (  # noqa: F401
    REPLAY_CONFLICT,
    REPLAY_HIT,
    REPLAY_NEW,
    InFlightLimiter,
    ReceiptLedger,
)
