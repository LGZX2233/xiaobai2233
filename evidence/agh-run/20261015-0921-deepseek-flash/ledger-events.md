# Kernel ledger of this run (read-only copy of <PK_ROOT>/demo.sqlite)

Committed events (command bookkeeping `command.committed` omitted):
- commit 10.0  design.confirmed
- commit 13.0  rules.published
- commit 34.0  verification.recorded
- commit 37.0  verification.recorded
- commit 38.0  attempt.selected
- commit 39.0  delivery_snapshot.frozen
- commit 39.1  approval.requested
- commit 40.0  approval.decided
- commit 41.0  delivery.claimed
- commit 42.0  blocker.opened
- commit 43.0  blocker.resolved

commit_log rows: 43

Current heads of the interesting object types:
- approval approval-request-cfdd04d795e587903e4d: {"status": "approved", "decision": "approved"}
- attempt attempt-5bc5ea7a0b1d42b9: {"status": "completed", "strategy_id": "s2"}
- attempt attempt-cfd5413aeb6f4f4d: {"status": "unknown", "strategy_id": "s3"}
- attempt attempt-f23fb274a0bd4303: {"status": "completed", "strategy_id": "s1"}
- delivery operation-bd976d2755e420cf0a0d: {"status": "applied"}
- selection selection-4a4101b08f4d: {"reason": "Only s2 passed the independent check (alpha_fit 0.37286 agrees with the closed-form 0.3786), while s1 failed the check and s3 settled as unknown."}
- verification verification-808176b32751: {"result": "passed"}
- verification verification-d21b37a0b76a: {"result": "failed"}
