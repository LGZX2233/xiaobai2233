"""Human approval entry for the AGH heat-inversion demo (terminal, outside the agent).

The AGH plugin can request delivery but has no approval tool: approval.decide is a
human-only kernel command. This script opens the same project store the running AGH
host uses (SQLite WAL plus the shared access fence allow several writers at once),
lists pending approvals and decides one through ``build_human_server``.

What the person has to do: look at the listed snapshot, then type the first 8 hex
characters of its digest to approve, or ``r`` plus a typed reason to reject.

The TTY check and the typed digest prefix are an *interaction proof*, not a security
boundary: they show that a person at a terminal looked at this snapshot. Anyone with
shell access to this machine can run this script or call ``decide`` directly. The kernel
runs here in evidence mode "test"; the decision is recorded under the principal
"human-operator" with the interaction source "terminal-typed-digest-prefix".

Usage:
    python tools/pk_human_approve.py [--root <PK_ROOT>]
Without --root the run directory written by the plugin to
<tempdir>/pk-agh-last-root.txt is used.

Non-interactive core (used by tests and by the rehearsal script, never by the agent):
    decide(root, approval_id, digest_prefix, decision, reason)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from project_kernel.bootstrap import InvocationContextRegistry, build_human_server  # noqa: E402
from project_kernel.contracts import ALL_CAPABILITIES  # noqa: E402
from project_kernel.contracts.dto import ObjectRef  # noqa: E402
from project_kernel.data.store.store import Store  # noqa: E402
from project_kernel.interfaces.rpc.framing import decode_frame, encode_frame  # noqa: E402
from project_kernel.interfaces.rpc.invocation import InteractionProof  # noqa: E402

PROJECT_ID = "agh-heat-demo"
STORE_ID = "agh-heat-store"
POINTER = "pk-agh-last-root.txt"
HUMAN_PRINCIPAL = "human-operator"
HUMAN_HANDLE = "human-terminal-handle"
PROOF_SOURCE = "terminal-typed-digest-prefix"
PREFIX_LEN = 8
_HEX_PREFIX = re.compile(r"^[0-9a-f]{%d,64}$" % PREFIX_LEN)


class ApprovalError(Exception):
    """A refusal shown to the person; never a crash trace."""


def default_root() -> Path:
    pointer = Path(tempfile.gettempdir()) / POINTER
    try:
        text = pointer.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ApprovalError(f"找不到运行目录指针 {pointer}：请先在 AGH 里让智能体调用一次工具，或用 --root 指定。") from exc
    if not text:
        raise ApprovalError(f"运行目录指针 {pointer} 是空的：请先在 AGH 里让智能体调用一次工具，或用 --root 指定。")
    return Path(text)


def open_store(root: Path) -> Store:
    db = Path(root) / "demo.sqlite"
    if not db.exists():
        raise ApprovalError(f"{db} 不存在：这不是插件的运行目录。")
    return Store.open_project(db, PROJECT_ID, STORE_ID)


def _payload(store: Store, kind: str, ref_or_id: Any) -> dict[str, Any] | None:
    if isinstance(ref_or_id, dict):
        ref = ObjectRef.from_dict(ref_or_id)
    else:
        head = store.get_head(kind, str(ref_or_id), "current")
        if head is None:
            return None
        ref = ObjectRef(PROJECT_ID, kind, str(ref_or_id), head["revision_id"])
    revision = store.get_revision(ref)
    return None if revision is None else revision["payload"]


def _alpha_fit(store: Store, attempt: dict[str, Any]) -> float | None:
    """The solver's own alpha_fit for display; the independent check already ran in the kernel."""
    try:
        root_payload = _payload(store, "execution_root", attempt["execution_root_ref"])
        data = json.loads((Path(root_payload["path"]) / "result.json").read_text(encoding="utf-8"))
        return data.get("alpha_fit")
    except (KeyError, TypeError, OSError, ValueError):
        return None


def pending_approvals(store: Store) -> list[dict[str, Any]]:
    rows = store.conn.execute(
        "SELECT object_id FROM entity_head WHERE project_id=? AND type='approval' AND pointer_name='current'"
        " ORDER BY object_id", (PROJECT_ID,)).fetchall()
    found = []
    for (approval_id,) in rows:
        approval = _payload(store, "approval", approval_id) or {}
        if approval.get("status") != "pending":
            continue
        snapshot = _payload(store, "delivery_snapshot", approval.get("snapshot_id")) or {}
        body = snapshot.get("body", {})
        attempt = (_payload(store, "attempt", body["selected_attempt_ref"])
                   if body.get("selected_attempt_ref") else None) or {}
        found.append({
            "approval_id": approval_id,
            "snapshot_digest": approval.get("snapshot_digest"),
            "strategy_id": attempt.get("strategy_id"),
            "attempt_id": (body.get("selected_attempt_ref") or {}).get("object_id"),
            "alpha_fit": _alpha_fit(store, attempt) if attempt else None,
            "evidence_mode": body.get("evidence_mode"),
        })
    return found


def check_prefix(digest: str, typed: str) -> None:
    """Accept only a hex prefix of at least PREFIX_LEN characters that starts the digest."""
    typed = (typed or "").strip().lower()
    if not _HEX_PREFIX.match(typed):
        raise ApprovalError(f"请输入快照摘要的前 {PREFIX_LEN} 位十六进制字符，未做任何决定")
    if not digest or not digest.startswith(typed):
        raise ApprovalError("输入的摘要前缀与快照不一致，未做任何决定")


def decide(root: Path, approval_id: str, digest_prefix: str, decision: str, reason: str,
           *, proof_source: str = PROOF_SOURCE) -> dict[str, Any]:
    """Non-interactive core: decide one pending approval if the typed prefix matches its digest.

    Works while the AGH host process holds the same store open. The digest sent to the kernel
    is the one stored in the ledger, never the typed text.
    """
    if decision not in ("approved", "rejected"):
        raise ApprovalError("decision 只能是 approved 或 rejected")
    if not reason or not reason.strip():
        raise ApprovalError("必须填写理由")
    store = open_store(Path(root))
    try:
        entry = next((e for e in pending_approvals(store) if e["approval_id"] == approval_id), None)
        if entry is None:
            raise ApprovalError(f"没有待审批的 {approval_id}（可能已被处理）")
        digest = entry["snapshot_digest"] or ""
        check_prefix(digest, digest_prefix)
        registry = InvocationContextRegistry(handle_factory=lambda: HUMAN_HANDLE)
        registry.mint_human(HUMAN_PRINCIPAL, ALL_CAPABILITIES, project_id=PROJECT_ID,
                            proof=InteractionProof(proof_source, True))
        server = build_human_server(store, principal=HUMAN_PRINCIPAL, contexts=registry, mode="test")
        request = {"jsonrpc": "2.0", "id": "human-decide", "method": "kernel.command", "params": {
            "protocol_version": "1.0.0", "invocation_context_id": HUMAN_HANDLE,
            "selector": {"project_id": PROJECT_ID}, "command": "approval.decide",
            "payload": {"approval_id": approval_id, "snapshot_digest": digest,
                        "decision": decision, "reason": reason.strip()},
            "expected_heads": [], "idempotency_key": f"human-decide:{approval_id}:{decision}"}}
        response = decode_frame(server.handle_line(encode_frame(request)))
        if "error" in response:
            data = response["error"].get("data") or {}
            raise ApprovalError(f"内核拒绝：{data.get('code') or response['error'].get('message')}")
        receipt = response["result"]["receipt"]
        if receipt.get("status") == "rejected":
            raise ApprovalError(f"内核拒绝：{(receipt.get('error') or {}).get('code')}")
        status = (_payload(store, "approval", approval_id) or {}).get("status")
        return {"approval_id": approval_id, "decision": decision, "approval_status": status,
                "receipt_status": receipt.get("status"), "snapshot_digest": digest}
    finally:
        store.close()


def _show(entries: list[dict[str, Any]]) -> None:
    for number, e in enumerate(entries, 1):
        alpha = "未知" if e["alpha_fit"] is None else f"{e['alpha_fit']:.5f}"
        print(f"[{number}] 审批编号: {e['approval_id']}")
        print(f"    选中策略: {e['strategy_id'] or '未知'}  尝试: {e['attempt_id'] or '未知'}")
        print(f"    alpha_fit（求解器自报，已经内核独立校验）: {alpha}")
        print(f"    证据模式: {e['evidence_mode']}")
        print(f"    快照摘要: {e['snapshot_digest']}")


def interactive(root: Path) -> int:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("拒绝：人工审批必须在交互式终端中由人亲自输入（检测不到 TTY）。"
              "请直接在 PowerShell 窗口运行 tools\\pk-human-approve.ps1。", file=sys.stderr)
        return 2
    print(f"运行目录: {root}")
    store = open_store(root)
    try:
        entries = pending_approvals(store)
    finally:
        store.close()
    if not entries:
        print("没有待审批的交付请求。")
        return 0
    _show(entries)
    chosen = entries[0]
    try:
        if len(entries) > 1:
            pick = input(f"选择要处理的序号 (1-{len(entries)}): ").strip()
            if not pick.isdigit() or not 1 <= int(pick) <= len(entries):
                print("已取消，未做任何决定。")
                return 1
            chosen = entries[int(pick) - 1]
        answer = input(f"批准请输入快照摘要前 {PREFIX_LEN} 位；输入 r 拒绝；直接回车取消: ").strip()
        if not answer:
            print("已取消，未做任何决定。")
            return 1
        if answer.lower() == "r":
            reason = input("拒绝理由（必填）: ").strip()
            decision = "rejected"
            typed = (chosen["snapshot_digest"] or "")[:PREFIX_LEN]
        else:
            reason = input("批准理由（回车使用默认）: ").strip() or "人工核对快照摘要后批准"
            decision = "approved"
            typed = answer
        result = decide(root, chosen["approval_id"], typed, decision, reason)
    except (EOFError, KeyboardInterrupt):
        print("\n已取消，未做任何决定。")
        return 1
    except ApprovalError as exc:
        print(f"未完成：{exc}", file=sys.stderr)
        return 1
    label = "已批准" if result["decision"] == "approved" else "已拒绝"
    print(f"{label}：{result['approval_id']}（审批状态 {result['approval_status']}）。")
    if result["decision"] == "approved":
        print("现在回到 AGH 告诉智能体“已批准”，它会调用 pk_apply_delivery 完成交付。")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description="人工审批 Project Kernel 交付请求")
    parser.add_argument("--root", type=Path, help="插件运行目录（默认读取临时目录中的指针文件）")
    args = parser.parse_args(argv)
    try:
        root = (args.root or default_root()).resolve()
        return interactive(root)
    except ApprovalError as exc:
        print(f"未完成：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
