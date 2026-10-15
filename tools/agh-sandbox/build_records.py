#!/usr/bin/env python3
"""Turn one recorded AGH run into judge-readable records (no keys, relative paths).

Inputs are produced by the run itself: the AGH session export (`agh export <id> --format agnes`
and `--html`), the kernel store of that run (<PK_ROOT>/demo.sqlite, opened read-only) and the genuine
pty transcript of the human approval. Output folder gets:
  session.agnes.jsonl, session.html      AGH's own redacted export
  tool-chain.md / tool-chain.json        timestamp, tool, arguments, result summary
  ledger-events.md                       committed kernel events + current approval/delivery state
  human-approval-terminal.txt            the terminal transcript of tools/pk_human_approve.py
  versions.json                          node / AGH / plugin / python / model id as reported
Usage:
  python3 build_records.py --export-dir D --pk-root R --terminal T.txt --model M --out OUT \
      --kernel-dir K [--plugin-version 0.3.1] [--note TEXT]
"""
import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


def scrub(text, mapping):
    for old, new in mapping.items():
        text = text.replace(old, new)
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export-dir", required=True)
    ap.add_argument("--pk-root", required=True)
    ap.add_argument("--terminal", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--kernel-dir", required=True)
    ap.add_argument("--plugin-version", default="")
    ap.add_argument("--agh-version", default="")
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    exp = Path(a.export_dir)
    mapping = {a.pk_root: "<PK_ROOT>", a.kernel_dir: "<KERNEL>", "/tmp/agh_home": "<AGH_HOME>",
               "/tmp/aghrt": "<AGH_RUNTIME>"}

    raw = (exp / "session.agnes.jsonl").read_text(encoding="utf-8")
    (out / "session.agnes.jsonl").write_text(scrub(raw, mapping), encoding="utf-8")
    if (exp / "session.html").exists():
        shutil.copyfile(exp / "session.html", out / "session.html")
        html = (out / "session.html")
        html.write_text(scrub(html.read_text(encoding="utf-8"), mapping), encoding="utf-8")

    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    names, calls = {}, []
    models = []
    approvals = []
    for r in rows:
        d = r.get("data") or {}
        kind = r["type"]
        if kind == "tool/call":
            names[d["toolUseId"]] = len(calls)
            calls.append({"seq": r["seq"], "time_utc": r["ts"], "tool": d["name"], "arguments": d.get("args"),
                          "result_seq": None, "is_error": None, "result_summary": None})
        elif kind == "tool/result" and d.get("toolUseId") in names:
            entry = calls[names[d["toolUseId"]]]
            text = "".join(c.get("text", "") for c in d.get("content", []))
            entry.update(result_seq=r["seq"], is_error=bool(d.get("isError")), result_summary=scrub(text, mapping)[:400],
                         error_code=d.get("code"))
        elif kind == "cost/ledger" and (d.get("model") not in models):
            models.append(d.get("model"))
        elif kind in ("approval/asked", "approval/decided"):
            approvals.append({"seq": r["seq"], "type": kind, "summary": d.get("summary"), "verdict": d.get("verdict"),
                              "via": d.get("via")})
    (out / "tool-chain.json").write_text(json.dumps({"calls": calls, "agh_approval_events": approvals},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["| # | time (UTC) | tool | arguments | result (first 160 chars) |", "|---|---|---|---|---|"]
    for i, c in enumerate(calls, 1):
        res = (c["result_summary"] or "").replace("|", "\\|").replace("\n", " ")[:160]
        flag = f" [ERROR {c.get('error_code')}]" if c["is_error"] else ""
        args = json.dumps(c["arguments"], ensure_ascii=False)[:90].replace("|", "\\|")
        lines.append(f"| {i} | {c['time_utc'][11:23]} | {c['tool']} | `{args}` | {flag}{res} |")
    lines += ["", "AGH approval events (the model cannot answer these):"]
    lines += [f"- seq {x['seq']} {x['type']} {x.get('summary') or ''} {x.get('verdict') or ''} {x.get('via') or ''}" for x in approvals]
    (out / "tool-chain.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    ledger = ["# Kernel ledger of this run (read-only copy of <PK_ROOT>/demo.sqlite)", ""]
    try:
        con = sqlite3.connect(f"file:{a.pk_root}/demo.sqlite?mode=ro", uri=True)
        ledger.append("Committed events (command bookkeeping `command.committed` omitted):")
        for seq, idx, etype in con.execute("SELECT commit_seq,event_index,event_type FROM audit_event "
                                           "WHERE event_type!='command.committed' ORDER BY commit_seq,event_index"):
            ledger.append(f"- commit {seq}.{idx}  {etype}")
        total = con.execute("SELECT COUNT(*) FROM commit_log").fetchone()[0]
        ledger.append(f"\ncommit_log rows: {total}\n\nCurrent heads of the interesting object types:")
        q = ("SELECT h.type,h.object_id,r.payload_json FROM entity_head h JOIN revision r ON r.project_id=h.project_id "
             "AND r.type=h.type AND r.object_id=h.object_id AND r.revision_id=h.revision_id "
             "WHERE h.pointer_name='current' AND h.type IN ('approval','delivery','selection','verification','attempt') "
             "ORDER BY h.type,h.object_id")
        for typ, oid, payload in con.execute(q):
            try:
                p = json.loads(payload)
                keep = {k: p[k] for k in ("status", "strategy_id", "result", "decision", "state", "reason") if k in p}
            except ValueError:
                keep = {}
            ledger.append(f"- {typ} {oid}: {json.dumps(keep, ensure_ascii=False)}")
        con.close()
    except Exception as exc:  # the records stay useful without the ledger part
        ledger.append(f"(ledger not readable: {type(exc).__name__}: {exc})")
    (out / "ledger-events.md").write_text(scrub("\n".join(ledger) + "\n", mapping), encoding="utf-8")

    term = Path(a.terminal).read_text(encoding="utf-8")
    (out / "human-approval-terminal.txt").write_text(scrub(term, mapping), encoding="utf-8")

    def run(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.strip()
        except Exception:
            return ""
    versions = {"model_ids_in_session_cost_ledger": models, "requested_model": a.model,
                "agh_version_output": a.agh_version, "plugin": "@project-kernel/agh-plugin@" + a.plugin_version,
                "python": run(["/tmp/pkvenv/bin/python", "--version"]), "node": run(["/tmp/node-v24.22.0-linux-x64/bin/node", "--version"]),
                "evidence_mode": "test", "isolation": "directory_only", "note": a.note}
    (out / "versions.json").write_text(json.dumps(versions, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"records written to {out}: {len(calls)} tool calls, models {models}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
