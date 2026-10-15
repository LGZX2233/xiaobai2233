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
- approval approval-request-6a27d7372a2dc66a227f: {"status": "approved", "decision": "approved"}
- attempt attempt-80a57346a4f542d6: {"status": "unknown", "strategy_id": "s3"}
- attempt attempt-a26d8b15633140c5: {"status": "completed", "strategy_id": "s1"}
- attempt attempt-cb4348ba997a4490: {"status": "completed", "strategy_id": "s2"}
- delivery operation-bd6859b77ff86488622c: {"status": "applied"}
- selection selection-729d74f93c4c: {"reason": "s2（黄金分割搜索）是唯一通过独立验证的策略：其反演结果 alpha_fit=0.37286 与闭式解 0.3786 一致；s1 网格搜索未通过（拟合 0.3500 与闭式解不符），s3 为失败样本结果未知。"}
- verification verification-1b113e070376: {"result": "passed"}
- verification verification-ca367208b473: {"result": "failed"}
