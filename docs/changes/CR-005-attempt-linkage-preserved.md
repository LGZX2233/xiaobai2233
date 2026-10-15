# CR-005：attempt 结算必须保留 task/packet/strategy 关联（P03）

- 提出者：P13（集成验收，源自 P04 handoff 的 CR-2「settle 丢失 task_ref」）
- 目标 owner：P03（`src/project_kernel/application/attempt/service.py`）
- 关联：AC12–AC17（派发→执行→验收闭环）、AC30（追溯）、设计 02「对象采用明确 schema 的
  revision payload」+ 设计 03「新 attempt 关联修复链」
- 结论：**已由 P13 直接修复并加回归测试**（owner 不在线；缺陷影响最新 revision 读模型，
  属集成阻断级；改动只追加字段，不改契约/DDL）

## 1. 现象

`attempt_start` 在起始 revision 里写入 `task_ref / packet_ref / strategy_id / mode`；
随后的 `_settle`（running/completed/failed/unknown）与 `attempt_cancel` 只写
`status/exit_code/execution_handle_id`，**丢掉上述关联字段**。

P06 的读模型（`QueryService.latest_revisions`）与 P04 的事实驱动追赶都取「每 object 最新
revision」，因此一旦结算，attempt→task / attempt→packet 的追溯边就没有了；P04 只能绕道实现，
审计与 `S06 attempts.compare`/trace 也读不到 probe 来源。

## 2. 修复

`_apply_attempt_status()` 与 `attempt_cancel()` 在构造新 revision body 时，从当前 head 的
revision payload 携带稳定关联字段（仅当存在时写入）：

```python
for key in ("task_ref", "packet_ref", "strategy_id", "mode"):
    if prior.get(key) is not None:
        body[key] = prior[key]
```

只做「追加不丢字段」，未改命令入参、状态转移规则或 receipt 结构。

## 3. 证据

- 回归：`tests/p03_attempt/test_attempt.py::test_settled_attempt_keeps_task_packet_and_strategy_linkage`
  （真实 subprocess provider + 真实临时 SQLite；断言结算后最新 revision 仍带
  `task_ref/packet_ref/strategy_id`）。
- 回归范围：`tests\p03_attempt tests\p04_delivery tests\p06_queries tests\p09_corpus`
  → 130 passed；全量见 G2 报告。

## 4. 未变的边界

未改 `contracts/`、schema/DDL、公共 DTO、错误码；未引入新命令。P04 handoff 的 CR-2 中
「attempt 不推进 Task phase」未在本 CR 内处理（P04 以事实驱动追赶，且明确不伪造
`delivery_ready`），仍作为记录在案的缺口。
