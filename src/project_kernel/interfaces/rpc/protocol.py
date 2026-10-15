"""Pure protocol server: initialize / command / query dispatch with strict
schema boundaries. Business handlers are injected; this module performs no I/O
beyond framing and delegates validated payloads to typed handlers.

Entry order for ``kernel.command`` (design 04 §1/§2/§3):

1. envelope schema — unknown fields, bad ids, unknown commands are INVALID_INPUT;
2. human-only refusal — UNSUPPORTED_COMMAND before any payload verdict;
3. machine allowlist / declared surface — UNSUPPORTED_COMMAND;
4. invocation handle resolution — PERMISSION_DENIED for unminted or expired;
5. strict domain payload schema — INVALID_INPUT;
6. in-flight limit — retryable TEMPORARY_UNAVAILABLE;
7. receipt replay cache — original receipt, or IDEMPOTENCY_CONFLICT;
8. injected business handler.

The resolved handle is never handed to the handler (a ContextVar carries the
trusted context instead) and never logged, hashed or copied into a payload.
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Callable, Mapping

from ...contracts import (
    ValidationError,
    validate_command_envelope,
    validate_command_payload,
    validate_initialize_request,
    validate_query_envelope,
    validate_query_payload,
)
from ...contracts.digest import compute_bundle_digest
from ...contracts.errors import (
    BlockError,
    KernelError,
    capability_unavailable,
    idempotency_conflict,
    temporary_unavailable,
    unsupported_command,
)
from .commands import compute_input_hash
from .framing import (
    MAX_FRAME_BYTES_DEFAULT,
    FrameError,
    FrameTooLarge,
    LineFramer,
    decode_frame,
    encode_frame,
)
from .invocation import (
    CURRENT_MACHINE_CONTEXT,
    MachineContext,
    current_machine_context,
    resolve_context,
    sanitize_for_log,
    strip_invocation_context,
)
from .policy import HUMAN_ONLY_COMMANDS, CommandSurface
from .session import REPLAY_CONFLICT, REPLAY_HIT, InFlightLimiter, ReceiptLedger

_LOGGER = logging.getLogger("project_kernel.rpc")
_RPC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class Limits:
    def __init__(self, max_frame_bytes: int = MAX_FRAME_BYTES_DEFAULT, max_inflight: int = 4):
        self.max_frame_bytes = max_frame_bytes
        self.max_inflight = max_inflight

    def to_dict(self) -> dict[str, int]:
        return {"max_frame_bytes": self.max_frame_bytes, "max_inflight": self.max_inflight}


class ProtocolServer:
    def __init__(self, *, mode: str, supported_commands: list[str],
                 supported_queries: list[str], provider_capabilities: list[dict[str, Any]] | None = None,
                 limits: Limits | None = None,
                 command_handler: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
                 query_handler: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
                 server_instance_id: str | None = None,
                 allowlist: Any | None = None,
                 human_only_commands: Any = HUMAN_ONLY_COMMANDS,
                 context_resolver: Callable[[str], Any] | None = None,
                 receipt_ledger: ReceiptLedger | None = None,
                 inflight: Any | None = None,
                 command_handlers: Mapping[str, Callable[[str, dict[str, Any]], dict[str, Any]]] | None = None,
                 logger: logging.Logger | None = None,
                 command_authorizer: Callable | None = None):
        self.mode = mode
        self.supported_commands = list(supported_commands)
        self.supported_queries = list(supported_queries)
        self.provider_capabilities = provider_capabilities or []
        self.limits = limits or Limits()
        self.command_handler = command_handler
        self.query_handler = query_handler
        self.server_instance_id = server_instance_id or ("srv-" + uuid.uuid4().hex)
        self.human_only_commands = frozenset(human_only_commands or ())
        self.surface: CommandSurface | None = None
        if allowlist is not None:
            # A contradiction between the declared surface and the machine
            # allowlist fails loudly at composition time, never silently.
            self.surface = CommandSurface(allowlist=frozenset(allowlist),
                                          supported=frozenset(self.supported_commands),
                                          human_only=self.human_only_commands)
        self.context_resolver = context_resolver
        self.receipt_ledger = receipt_ledger
        self.command_authorizer = command_authorizer
        # The advertised max_inflight is enforced, not decorative.
        self.inflight = inflight if inflight is not None else InFlightLimiter(
            self.limits.max_inflight)
        self.command_handlers = dict(command_handlers or {})
        self.logger = logger or _LOGGER
        self._framer = LineFramer(self.limits.max_frame_bytes)

    # -- lifecycle --------------------------------------------------------
    def initialize_result(self) -> dict[str, Any]:
        declared = (list(self.surface.declared()) if self.surface is not None
                    else list(self.supported_commands))
        return {
            "protocol_version": "1.0.0",
            "schema_bundle_digest": compute_bundle_digest(),
            "server_instance_id": self.server_instance_id,
            "mode": self.mode,
            "supported_commands": declared,
            "supported_queries": list(self.supported_queries),
            "provider_capabilities": self.provider_capabilities,
            "limits": self.limits.to_dict(),
        }

    def feed(self, chunk: bytes) -> list[bytes]:
        """Consume a raw stdio chunk and answer every complete frame it held."""
        responses: list[bytes] = []
        try:
            frames = self._framer.feed(chunk)
        except FrameTooLarge as exc:
            self._framer.reset()
            for frame in exc.frames:      # valid frames that shared the chunk
                responses.append(self.handle_line(frame))
            responses.append(self._encode(_rpc_error(None, -32600, str(exc))))
            return responses
        for frame in frames:
            responses.append(self.handle_line(frame))
        return responses

    def replay_receipt(self, principal_id: str,
                       idempotency_key: str) -> Mapping[str, Any] | None:
        """Re-read a receipt the server already returned, for reconnect recovery."""
        if self.receipt_ledger is None:
            return None
        return self.receipt_ledger.lookup(principal_id, idempotency_key)

    # -- dispatch ---------------------------------------------------------
    def handle_line(self, line: bytes) -> bytes:
        try:
            msg = decode_frame(line, self.limits.max_frame_bytes)
        except FrameTooLarge:
            return self._encode(_rpc_error(None, -32600, "Frame too large"))
        except FrameError as exc:
            return self._encode(_rpc_error(None, -32700, f"Parse error: {exc}"))

        rpc_id = _safe_rpc_id(msg.get("id"))
        method = msg.get("method")
        if not isinstance(method, str):
            return self._encode(_rpc_error(rpc_id, -32600, "Invalid Request"))

        try:
            response = self._dispatch(msg, rpc_id, method)
        except (ValidationError, KernelError) as exc:
            response = _block_error(rpc_id, exc.error)
        except Exception as exc:  # never leak payload/handle text to the client
            response = _block_error(rpc_id, temporary_unavailable(
                f"unexpected server error ({type(exc).__name__})"))
        return self._encode(response)

    def _dispatch(self, msg: dict[str, Any], rpc_id: Any, method: str) -> dict[str, Any]:
        if method == "kernel.initialize":
            validate_initialize_request(msg)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": self.initialize_result()}
        if method == "kernel.command":
            return self._handle_command(msg, rpc_id)
        if method == "kernel.query":
            return self._handle_query(msg, rpc_id)
        return _rpc_error(rpc_id, -32601, f"Method not found: {method}")

    def _handle_command(self, msg: dict[str, Any], rpc_id: Any) -> dict[str, Any]:
        validate_command_envelope(msg)
        params = msg["params"]
        command = params["command"]

        # 2/3. Surface verdicts precede any payload verdict: a caller that may
        # not run the command learns nothing about its payload contract.
        if command in self.human_only_commands:
            return _block_error(rpc_id, unsupported_command(
                f"{command} is human-only and is not served on the machine surface"))
        if self.surface is not None:
            refusal = self.surface.reject(command)
            if refusal is not None:
                return _block_error(rpc_id, refusal)
        elif command not in self.supported_commands:
            return _block_error(rpc_id, unsupported_command(
                f"command {command!r} not available"))

        # 4. Trusted handle, resolved once at the entry; it never travels on.
        context, handler_params = self._resolve(params)

        # 5. Strict domain payload.
        validate_command_payload(command, params["payload"])

        if self.command_authorizer is not None:
            self._call_handler(self.command_authorizer,command,handler_params,context)

        input_hash: str | None = None
        if self.receipt_ledger is not None:
            input_hash = compute_input_hash(command, params.get("selector"),
                                           params.get("expected_heads"),
                                           params.get("payload"))
            if context is None:
                # Composition error: idempotent replay needs a resolved principal.
                raise KernelError(capability_unavailable(
                    "receipt replay requires a resolved invocation context"))
            state, cached = self.receipt_ledger.begin(
                context.principal_id, params["idempotency_key"], input_hash)
            if state == REPLAY_HIT and cached is not None:
                self._log("kernel.command replay", command, params)
                return {"jsonrpc": "2.0", "id": rpc_id, "result": {"receipt": dict(cached)}}
            if state == REPLAY_CONFLICT:
                raise KernelError(idempotency_conflict(
                    f"idempotency key {params['idempotency_key']!r} for {command} "
                    "was already used with different content"))

        handler = self.command_handlers.get(command) or self.command_handler
        if handler is None:
            return _block_error(rpc_id, capability_unavailable(
                "no command handler registered"))

        self._log("kernel.command", command, params)
        result = self._call_handler(handler, command, handler_params, context)
        if self.receipt_ledger is not None and context is not None:
            receipt = result.get("receipt") if isinstance(result, Mapping) else None
            self.receipt_ledger.record(context.principal_id, params["idempotency_key"],
                                       input_hash or "", receipt)
        return {"jsonrpc": "2.0", "id": rpc_id, "result": result}

    def _handle_query(self, msg: dict[str, Any], rpc_id: Any) -> dict[str, Any]:
        validate_query_envelope(msg)
        params = msg["params"]
        query = params["query"]
        if query not in self.supported_queries:
            return _block_error(rpc_id, unsupported_command(
                f"query {query!r} not available"))
        # read permission is re-checked for every query, receipts included
        context, handler_params = self._resolve(params)
        validate_query_payload(query, params["payload"])
        if self.query_handler is None:
            return _block_error(rpc_id, capability_unavailable(
                "no query handler registered"))
        self._log("kernel.query", query, params)
        result = self._call_handler(self.query_handler, query, handler_params, context)
        return {"jsonrpc": "2.0", "id": rpc_id, "result": result}

    # -- helpers ----------------------------------------------------------
    def _resolve(self, params: dict[str, Any]) -> tuple[MachineContext | None, dict[str, Any]]:
        if self.context_resolver is None:
            return None, dict(params)
        context = resolve_context(self.context_resolver,
                                  params.get("invocation_context_id"))
        return context, strip_invocation_context(params)

    def _call_handler(self, handler: Callable[[str, dict[str, Any]], Any], name: str,
                      handler_params: dict[str, Any],
                      context: MachineContext | None) -> Any:
        token = CURRENT_MACHINE_CONTEXT.set(context)
        acquired = False
        try:
            if self.inflight is not None:
                self.inflight.try_acquire()
                acquired = True
            result = handler(name, handler_params)
        finally:
            if acquired:
                self.inflight.release()
            CURRENT_MACHINE_CONTEXT.reset(token)
        if not isinstance(result, Mapping):
            raise KernelError(capability_unavailable(
                f"{name} handler returned a non-object result"))
        return dict(result)

    def _log(self, event: str, name: str, params: Mapping[str, Any]) -> None:
        if not self.logger.isEnabledFor(logging.DEBUG):
            return
        # handle-bearing fields are dropped, never logged
        self.logger.debug("%s name=%s params=%s", event, name,
                          sanitize_for_log(dict(params)))

    def _encode(self, response: dict[str, Any]) -> bytes:
        try:
            return encode_frame(response, self.limits.max_frame_bytes)
        except FrameTooLarge:
            # A handler returning more than one frame must hand back an artifact
            # reference instead; oversize is never silently truncated.
            fallback = _block_error(_safe_rpc_id(response.get("id")), capability_unavailable(
                "response exceeds max_frame_bytes; return an artifact reference"))
        except FrameError:
            fallback = _rpc_error(_safe_rpc_id(response.get("id")), -32603, "Internal error")
        try:
            return encode_frame(fallback, self.limits.max_frame_bytes)
        except FrameError:
            return b'{"jsonrpc":"2.0","id":null,"error":{"code":-32603,"message":"Internal error"}}\n'


def _safe_rpc_id(value: Any) -> str | None:
    """Return IDs matching the frozen v1 pattern, with its existing anchor semantics."""
    return value if isinstance(value, str) and _RPC_ID_RE.match(value) else None


def _rpc_error(rpc_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rpc_id,
            "error": {"code": code, "message": message}}


def _block_error(rpc_id: Any, error: BlockError) -> dict[str, Any]:
    """Business error as a JSON-RPC application error.

    ``data`` carries the frozen block_error object
    (common.schema.json#/$defs/block_error) — the same shape a rejected
    CommandReceipt uses — so a client reads retryable/category/recovery_action
    instead of parsing a message string.
    """
    return {"jsonrpc": "2.0", "id": rpc_id,
            "error": {"code": -32602, "message": error.message, "data": error.to_dict()}}
