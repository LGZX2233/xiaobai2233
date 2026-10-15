// Owns the Python kernel host process and the bridge client bound to it.
// Only the machine channel exists here; the host process has no human entry.
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { ProtocolClient, ProtocolError } from "./vendor/client.mjs";

export class KernelSession {
  constructor({ python, hostScript, root, pollTimeoutSec = 3, requestTimeoutMs = 60000 }) {
    this.python = python;
    this.hostScript = hostScript;
    this.root = root;
    this.pollTimeoutSec = pollTimeoutSec;
    this.requestTimeoutMs = requestTimeoutMs;
    this.child = null;
    this.client = null;
    this.state = null;
    this.stderr = "";
    this.startPromise = null;
    this.closePromise = null;
    this.closed = false;
  }

  start(readState) {
    if (this.closed) return Promise.reject(new ProtocolError("SESSION_CLOSED", "kernel session is closed"));
    this.startPromise ??= this.#start(readState);
    return this.startPromise;
  }

  async #start(readState) {
    // -I ignores PYTHONDONTWRITEBYTECODE; -B also protects the source tree in isolated mode.
    this.child = spawn(this.python, ["-I", "-B", "-X", "utf8", this.hostScript, "--root", this.root,
      "--poll-timeout", String(this.pollTimeoutSec)], { windowsHide: true });
    this.child.stderr.on("data", (bytes) => { this.stderr += bytes.toString("utf8"); });
    this.exited = new Promise((resolve) => this.child.once("close", resolve));
    this.client = new ProtocolClient({
      machineContextId: "agh-machine-handle",
      requestTimeoutMs: this.requestTimeoutMs,
      write: (bytes) => this.child.stdin.write(bytes),
    });
    this.child.stdout.on("data", (bytes) => this.client.onData(bytes));
    this.child.on("error", (error) => this.client.close(error));
    this.child.stdin.on("error", (error) => this.client.close(error));
    this.child.once("close", (code, signal) => this.client.close(new ProtocolError(
      "HOST_EXITED", `kernel host exited (${signal ?? code}); ${this.stderr.trim()}`)));
    try {
      await this.client.initialize("agh-plugin");
      this.state = await readState(this.root);
      if (this.closed) throw new ProtocolError("SESSION_CLOSED", "kernel session closed during startup");
      return this.state;
    } catch (error) {
      await this.close();
      throw error;
    }
  }

  selector() {
    return { project_id: this.state.project_id };
  }

  // A fresh key per logical call; callers pass requestId back to retry the same call.
  async command(command, payload, requestId = randomUUID()) {
    const idempotencyKey = `${command}:${requestId}`;
    try {
      const response = await this.client.command({ command, selector: this.selector(), payload, idempotencyKey });
      return { requestId, receipt: response.receipt };
    } catch (error) {
      if (error instanceof ProtocolError && error.code === "COMMIT_OUTCOME_UNKNOWN") {
        const receipt = await this.client.recoverReceipt({ selector: this.selector(), idempotencyKey });
        return { requestId, receipt, recovered: true };
      }
      throw error;
    }
  }

  async query(query, payload = {}, asOfSeq, pageToken) {
    return (await this.queryEnvelope(query, payload, asOfSeq, pageToken)).data;
  }

  /** Return the RPC envelope, retaining watermarks, source gaps and pagination. */
  queryEnvelope(query, payload = {}, asOfSeq, pageToken) {
    return this.client.query({ query, selector: this.selector(), payload, asOfSeq, pageToken });
  }

  // Host-owned observation (not a kernel command): turns solver output into a candidate manifest.
  hostCall(method, params) {
    return this.client.request(method, params);
  }

  close() {
    this.closed = true;
    this.closePromise ??= this.#close();
    return this.closePromise;
  }

  async #close() {
    this.client?.close();
    if (!this.child) return;
    this.child.stdin.end();
    let timer;
    const exited = await Promise.race([
      this.exited.then(() => true),
      new Promise((resolve) => { timer = setTimeout(() => resolve(false), 5000); }),
    ]);
    clearTimeout(timer);
    if (!exited) {
      this.child.kill();
      await this.exited;
    }
  }
}
