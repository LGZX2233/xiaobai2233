// P10 stdio bridge client (pure TS/JS, no host SDK).
//
// Responsibilities (design 04 §1/§2/§3):
//   * newline framing over arbitrary byte chunks: partial frames, several
//     coalesced frames and a multi-byte UTF-8 character split across chunks;
//   * strict decoding: illegal UTF-8, duplicate JSON keys, non-finite numbers
//     and oversized frames are protocol failures, never silently accepted;
//   * responses are matched to requests by `id`, so out-of-order answers and
//     unknown/stale ids are handled without corrupting pending requests;
//   * the machine invocation context is attached at this tool boundary — a
//     payload/caller may never supply it, nor forge `actor_id`/`force`;
//   * a request timeout is NOT a cancellation: nothing is sent to cancel, and
//     recovery is a `command.receipt` re-read with the original key.

import { createHash } from "node:crypto";
import { canonicalize } from "./canonicalize.mjs";

export const MAX_FRAME_BYTES_DEFAULT = 1024 * 1024;
export const REQUEST_TIMEOUT_MS_DEFAULT = 30000;

//: envelope/params keys this client may put on the wire (contract is closed).
const ALLOWED_PARAM_KEYS = new Set([
  "protocol_version",
  "invocation_context_id",
  "idempotency_key",
  "command",
  "selector",
  "expected_heads",
  "payload",
  "query",
  "as_of_seq",
  "page_token",
]);

//: keys a model-facing caller must never smuggle in (identity/scope forging).
const FORBIDDEN_PAYLOAD_KEYS = new Set([
  "invocation_context_id",
  "actor_id",
  "principal_id",
  "capabilities",
  "force",
  "trusted_staged_locator_ref",
]);

const SELECTOR_ID_KEYS = ["project_id", "workspace_id", "session_id", "task_id", "attempt_id"];

export class ProtocolError extends Error {
  constructor(code, message, { retryable = false, data = null, rpcCode = null } = {}) {
    super(message);
    this.name = "ProtocolError";
    this.code = code;
    this.retryable = retryable;
    this.data = data;
    this.rpcCode = rpcCode;
  }
}

export function sha256HexOf(value) {
  return createHash("sha256").update(canonicalize(value), "utf8").digest("hex");
}

export function canonicalSelector(selector) {
  const out = {};
  if (!selector || typeof selector !== "object") return out;
  for (const key of SELECTOR_ID_KEYS) {
    const value = selector[key];
    if (typeof value === "string" && value.length > 0) out[key] = value;
  }
  return out;
}

// Same digest as project_kernel.interfaces.rpc.commands.compute_input_hash:
// command + canonical selector IDs + expected_heads + strict payload.
export function inputHash(command, selector, expectedHeads, payload) {
  return sha256HexOf({
    command,
    selector: canonicalSelector(selector),
    expected_heads: Array.isArray(expectedHeads) ? expectedHeads : [],
    payload: payload ?? {},
  });
}

function rejectDuplicateKeys(text) {
  // A minimal strict reader: JSON.parse silently keeps the last duplicate key,
  // which would let a peer smuggle two values for the same field.
  const seenKeys = [];
  let depth = 0;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (ch === '"') {
      let j = i + 1;
      let esc = false;
      for (; j < text.length; j += 1) {
        if (esc) esc = false;
        else if (text[j] === "\\") esc = true;
        else if (text[j] === '"') break;
      }
      let k = j + 1;
      while (k < text.length && /\s/.test(text[k])) k += 1;
      if (text[k] === ":") {
        let key;
        try {
          key = JSON.parse(text.slice(i, j + 1));
        } catch {
          throw new ProtocolError("PARSE_ERROR", "invalid JSON object key");
        }
        const bucket = seenKeys[depth] ?? (seenKeys[depth] = new Set());
        if (bucket.has(key)) {
          throw new ProtocolError("PARSE_ERROR", `duplicate JSON key ${key}`);
        }
        bucket.add(key);
      }
      i = j;
      continue;
    }
    if (ch === "{" || ch === "[") {
      depth += 1;
    } else if (ch === "}" || ch === "]") {
      seenKeys[depth] = undefined;
      depth -= 1;
    }
  }
}

function parseStrictFrame(frameBytes) {
  let text;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(frameBytes);
  } catch {
    throw new ProtocolError("PARSE_ERROR", "illegal UTF-8 in frame");
  }
  rejectDuplicateKeys(text);
  let value;
  try {
    value = JSON.parse(text);
  } catch (err) {
    throw new ProtocolError("PARSE_ERROR", `invalid JSON: ${err.message}`);
  }
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new ProtocolError("INVALID_REQUEST", "top-level JSON value must be an object");
  }
  const values = [value];
  while (values.length) {
    const item = values.pop();
    if (typeof item === "number" && !Number.isFinite(item)) {
      throw new ProtocolError("PARSE_ERROR", "non-finite JSON number");
    }
    if (item !== null && typeof item === "object") {
      for (const child of Object.values(item)) values.push(child);
    }
  }
  return value;
}

export class ProtocolClient {
  /**
   * @param {object} options
   * @param {(bytes: Buffer) => void} options.write  writes one framed request
   * @param {string} [options.machineContextId] trusted handle attached at this boundary
   * @param {number} [options.maxFrameBytes]
   * @param {number} [options.requestTimeoutMs]
   * @param {Function} [options.setTimer]
   * @param {Function} [options.clearTimer]
   */
  constructor({
    write,
    machineContextId = null,
    maxFrameBytes = MAX_FRAME_BYTES_DEFAULT,
    requestTimeoutMs = REQUEST_TIMEOUT_MS_DEFAULT,
    setTimer = setTimeout,
    clearTimer = clearTimeout,
    logger = null,
  } = {}) {
    if (typeof write !== "function") throw new TypeError("write callback is required");
    this.write = write;
    this.machineContextId = machineContextId;
    this.maxFrameBytes = maxFrameBytes;
    this.requestTimeoutMs = requestTimeoutMs;
    this.setTimer = setTimer;
    this.clearTimer = clearTimer;
    this.logger = logger;
    this.nextId = 1;
    this.pending = new Map();
    this.orphanResponses = [];
    this.buffer = Buffer.alloc(0);
    this.failed = null;
  }

  // -- framing ----------------------------------------------------------
  onData(chunk) {
    if (this.failed) return [];
    const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    this.buffer = Buffer.concat([this.buffer, bytes]);
    const handled = [];
    for (;;) {
      const idx = this.buffer.indexOf(0x0a);
      if (idx < 0) break;
      let frame = this.buffer.subarray(0, idx);
      this.buffer = this.buffer.subarray(idx + 1);
      if (frame.length > 0 && frame[frame.length - 1] === 0x0d) {
        frame = frame.subarray(0, frame.length - 1);
      }
      handled.push(this.#handleFrame(frame));
    }
    if (this.buffer.length > this.maxFrameBytes) {
      this.#fail(new ProtocolError("FRAME_TOO_LARGE",
        `frame exceeds ${this.maxFrameBytes} bytes`));
    }
    return handled.filter((entry) => entry !== null);
  }

  #fail(error) {
    this.failed = error;
    this.buffer = Buffer.alloc(0);
    for (const [, entry] of this.pending) {
      this.clearTimer(entry.timer);
      entry.reject(error);
    }
    this.pending.clear();
  }

  #handleFrame(frame) {
    let msg;
    try {
      if (frame.length > this.maxFrameBytes) {
        throw new ProtocolError("FRAME_TOO_LARGE", `frame exceeds ${this.maxFrameBytes} bytes`);
      }
      msg = parseStrictFrame(frame);
    } catch (err) {
      this.#fail(err);
      return null;
    }
    const id = msg.id == null ? null : String(msg.id);
    const entry = this.pending.get(id);
    if (!entry) {
      // Unknown / already-settled / duplicate id: never resolve the wrong waiter.
      this.orphanResponses.push(msg);
      if (this.logger) this.logger(`orphan response id=${id}`);
      return msg;
    }
    this.pending.delete(id);
    this.clearTimer(entry.timer);
    if (msg.error) {
      const data = msg.error.data ?? null;
      entry.reject(new ProtocolError(
        data?.code ?? `RPC_${msg.error.code}`,
        msg.error.message ?? "protocol error",
        { retryable: Boolean(data?.retryable), data, rpcCode: msg.error.code },
      ));
    } else if (msg.result === undefined) {
      entry.reject(new ProtocolError("INVALID_RESPONSE",
        "response carries neither result nor error"));
    } else {
      entry.resolve(msg.result);
    }
    return msg;
  }

  // -- request/response -------------------------------------------------
  request(method, params, { timeoutMs = this.requestTimeoutMs } = {}) {
    if (this.failed) return Promise.reject(this.failed);
    const id = `rpc-${this.nextId++}`;
    const message = { jsonrpc: "2.0", id, method, params };
    return new Promise((resolve, reject) => {
      const timer = this.setTimer(() => {
        this.pending.delete(id);
        // Deliberately does NOT send a cancel frame: a request timeout is not a
        // cancellation, and the original idempotency key stays valid for recovery.
        reject(new ProtocolError("COMMIT_OUTCOME_UNKNOWN",
          "request timed out; query command.receipt with the original key before retrying",
          { retryable: true, data: { id, method } }));
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timer, method });
      this.write(Buffer.from(`${JSON.stringify(message)}\n`, "utf8"));
    });
  }

  initialize(clientId = "bridge-client") {
    return this.request("kernel.initialize",
      { client_id: clientId, supported_protocol_versions: ["1.0.0"] });
  }

  query({ query, selector, payload = {}, asOfSeq = undefined, pageToken = undefined,
          timeoutMs } = {}) {
    const params = {
      protocol_version: "1.0.0",
      invocation_context_id: this.#contextId(selector),
      selector,
      query,
      payload: checkPayload(payload),
    };
    if (asOfSeq !== undefined) params.as_of_seq = String(asOfSeq);
    if (pageToken !== undefined) params.page_token = pageToken;
    return this.request("kernel.query", params, { timeoutMs });
  }

  /**
   * Send one machine command. `idempotencyKey` is mandatory and is meant to be
   * reused verbatim by a user retry.
   */
  command({ command, selector, payload = {}, expectedHeads = [], idempotencyKey,
            timeoutMs } = {}) {
    if (!idempotencyKey) {
      throw new ProtocolError("INVALID_INPUT",
        "idempotency_key is required and must be reused on retry");
    }
    const params = {
      protocol_version: "1.0.0",
      invocation_context_id: this.#contextId(selector),
      idempotency_key: idempotencyKey,
      command,
      selector,
      expected_heads: expectedHeads,
      payload: checkPayload(payload),
    };
    for (const key of Object.keys(params)) {
      if (!ALLOWED_PARAM_KEYS.has(key)) {
        throw new ProtocolError("INVALID_INPUT", `params may not carry ${key}`);
      }
    }
    return this.request("kernel.command", params, { timeoutMs });
  }

  /**
   * Recover after a timeout/disconnect: read the durable receipt for the same
   * principal + key + domain. Missing receipt means "unknown outcome", never
   * "succeeded".
   */
  async recoverReceipt({ idempotencyKey, receiptDomain = "project", selector,
                         timeoutMs } = {}) {
    if (!idempotencyKey) {
      throw new ProtocolError("INVALID_INPUT", "idempotency_key is required for recovery");
    }
    const result = await this.query({
      query: "command.receipt", selector,
      payload: { idempotency_key: idempotencyKey, receipt_domain: receiptDomain },
      timeoutMs,
    });
    return result?.data?.receipt ?? null;
  }

  #contextId(selector) {
    if (!this.machineContextId) {
      throw new ProtocolError("PERMISSION_DENIED",
        "no trusted machine invocation context is bound to this bridge");
    }
    return this.machineContextId;
  }

  close(error) {
    this.#fail(error ?? new ProtocolError("CLIENT_CLOSED", "bridge closed"));
  }
}

function checkPayload(payload) {
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
    throw new ProtocolError("INVALID_INPUT", "payload must be an object");
  }
  for (const key of Object.keys(payload)) {
    if (FORBIDDEN_PAYLOAD_KEYS.has(key)) {
      throw new ProtocolError("INVALID_INPUT",
        `payload may not carry ${key}; identity and scope are resolved by the trusted entry`);
    }
  }
  return payload;
}
