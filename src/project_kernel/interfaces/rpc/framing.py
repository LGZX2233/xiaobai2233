"""Strict JSON-RPC 2.0 stdio framing (one UTF-8 message per line).

stdout carries only protocol; stderr carries logs. Frame parsing rejects
duplicate JSON keys, non-finite numbers, illegal UTF-8, unpaired Unicode
surrogates, decoder recursion exhaustion and oversized frames.

``LineFramer`` is the byte-level stream state machine: a single ``read`` may
deliver a partial frame or several coalesced frames, so callers must feed
chunks and act on the returned complete frames (design 04 §1).
"""
from __future__ import annotations

import json
import math
from typing import Any, Sequence

MAX_FRAME_BYTES_DEFAULT = 1024 * 1024

#: initialize-result.schema.json requires ``limits.max_frame_bytes >= 1024``.
MIN_FRAME_BYTES = 1024

LINE_SEPARATOR = b"\n"


class FrameError(ValueError):
    pass


class FrameTooLarge(FrameError):
    """A frame exceeded its byte budget.

    ``frames`` carries the complete frames that were already extracted from the
    same chunk before the violation, so a caller can still answer them instead of
    silently dropping valid requests that happened to share a chunk with an
    oversized partial frame.
    """

    def __init__(self, message: str, frames: Sequence[bytes] = ()) -> None:
        super().__init__(message)
        self.frames = tuple(frames)


def parse_json_strict(data: bytes) -> Any:
    """Decode JSON, raising FrameError for invalid text or decoder depth limits."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FrameError("illegal UTF-8") from exc

    def _no_duplicates(pairs):
        out: dict[str, Any] = {}
        for k, v in pairs:
            if k in out:
                raise ValueError(f"duplicate key {k!r}")
            out[k] = v
        return out

    def _reject_constant(value):
        raise ValueError(f"non-finite number {value}")

    try:
        value = json.loads(text, object_pairs_hook=_no_duplicates,
                           parse_constant=_reject_constant)
        values = [value]
        while values:
            item = values.pop()
            if isinstance(item, str):
                item.encode("utf-8")
            if isinstance(item, float) and not math.isfinite(item):
                raise ValueError("non-finite JSON number")
            if isinstance(item, dict):
                values.extend(item.keys())
                values.extend(item.values())
            elif isinstance(item, list):
                values.extend(item)
        return value
    except RecursionError as exc:
        raise FrameError("JSON nesting exceeds decoder recursion limit") from exc
    except UnicodeEncodeError as exc:
        raise FrameError("unpaired Unicode surrogate") from exc
    except ValueError as exc:
        raise FrameError(str(exc)) from exc


def decode_frame(line: bytes, max_frame_bytes: int = MAX_FRAME_BYTES_DEFAULT) -> dict[str, Any]:
    if len(line) > max_frame_bytes:
        raise FrameTooLarge(f"frame exceeds {max_frame_bytes} bytes")
    obj = parse_json_strict(line)
    if not isinstance(obj, dict):
        raise FrameError("top-level JSON value must be an object")
    return obj


def encode_frame(obj: Any, max_frame_bytes: int = MAX_FRAME_BYTES_DEFAULT) -> bytes:
    """Encode one UTF-8 JSON line; serialization failures raise FrameError."""
    try:
        text = json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        data = (text + "\n").encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise FrameError("response cannot be encoded as UTF-8 JSON") from exc
    if len(data) > max_frame_bytes:
        raise FrameTooLarge(f"frame exceeds {max_frame_bytes} bytes")
    return data


class LineFramer:
    """Reassembles newline-delimited frames from arbitrary byte chunks.

    Byte-oriented on purpose: a multi-byte UTF-8 character split across two
    chunks stays intact because the buffer is never decoded until a full frame
    exists. A trailing CR is dropped so a CRLF client is still readable.
    """

    def __init__(self, max_frame_bytes: int = MAX_FRAME_BYTES_DEFAULT) -> None:
        if max_frame_bytes < MIN_FRAME_BYTES:
            raise ValueError(f"max_frame_bytes must be >= {MIN_FRAME_BYTES}")
        self.max_frame_bytes = max_frame_bytes
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> list[bytes]:
        """Append *chunk* and return every frame it completed, in order."""
        if not isinstance(chunk, (bytes, bytearray)):
            raise TypeError("chunk must be bytes")
        self._buf.extend(chunk)
        frames: list[bytes] = []
        while True:
            idx = self._buf.find(LINE_SEPARATOR)
            if idx < 0:
                break
            frame = bytes(self._buf[:idx])
            del self._buf[:idx + 1]
            if frame.endswith(b"\r"):
                frame = frame[:-1]
            frames.append(frame)
        if len(self._buf) > self.max_frame_bytes:
            # Do not keep growing an unusable partial frame; frames completed
            # earlier in this chunk are reported with the error.
            self._buf.clear()
            raise FrameTooLarge(f"frame exceeds {self.max_frame_bytes} bytes", frames)
        return frames

    def pending_bytes(self) -> int:
        return len(self._buf)

    def reset(self) -> None:
        self._buf.clear()
