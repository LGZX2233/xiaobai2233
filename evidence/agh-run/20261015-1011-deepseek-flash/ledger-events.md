# Kernel ledger of this run (read-only copy of <PK_ROOT>/demo.sqlite)

Committed events (command bookkeeping `command.committed` omitted):
- commit 10.0  design.confirmed
- commit 13.0  rules.published
- commit 31.0  verification.recorded
- commit 34.0  verification.recorded
- commit 35.0  attempt.selected
- commit 36.0  delivery_snapshot.frozen
- commit 36.1  approval.requested
- commit 37.0  approval.decided
- commit 38.0  delivery.claimed
- commit 39.0  blocker.opened
- commit 40.0  blocker.resolved

commit_log rows: 40

Current heads of the interesting object types:
- approval approval-request-0481f3a270639c3b42c8: {"status": "approved", "decision": "approved"}
- attempt attempt-cbef9b86e43f4114: {"status": "completed", "strategy_id": "s2"}
- attempt attempt-e4b36ba952fc45fd: {"status": "completed", "strategy_id": "s1"}
- delivery operation-700fa62c7ac596510312: {"status": "applied"}
- selection selection-9b1b434f4c5c: {"reason": "s2 passed independent verification (alpha=0.372861, ~1.5% from closed-form) while s1 failed (alpha=0.3500, ~7.5% off, outside 5%)."}
- verification verification-3dc9915b1437: {"result": "passed"}
- verification verification-930b625e550a: {"result": "failed"}
