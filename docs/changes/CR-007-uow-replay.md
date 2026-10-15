# CR-007：UoW 幂等重放与事务错误分类

- 范围：T01 / P01，复核问题 R08、R09。
- 日期：2026-10-09。
- 状态：实现完成，P01 定向 40 项通过；集成接受由 P13 记录。
- 影响消费者：所有使用 UnitOfWork 的命令；事务外启动执行的消费者可读取内部 `did_commit`。
- 公共契约：无新增字段、错误码或 DDL；本次恢复既有幂等和错误语义。CR-004 的锁内序号分配保留。

## 行为

[UnitOfWork](../../src/project_kernel/data/store/uow.py) 对 `retryable=True` 或 `category=unknown` 的 KernelError 回滚并抛出，不写拒绝回执、审计、业务 revision 或 head。基础设施恢复后，同一个 key 可以重新执行。非重试的稳定拒绝仍保存回执；包括目前标记为非重试的 `CAPABILITY_UNAVAILABLE`，此修复不改该错误的公共定义。

正常事务和拒绝事务都在取得写锁后重新查询幂等 key。另一个调用在回滚与重拿锁之间胜出时，同 hash 返回其完整回执，不同 hash 返回 `IDEMPOTENCY_CONFLICT`，不产生第二个事务序号或拒绝回执。

回执重放恢复全部现有字段，包括 error 的 code、message、retryable、category、safe_details、recovery_action、related_refs，保证 `to_dict()` 与持久化回执一致。

提交前 SQLite 失败或 COMMIT 失败后成功回滚时，返回 `SQLITE_BUSY` 或 `TEMPORARY_UNAVAILABLE`，不伪报提交结果未知。只有已尝试 COMMIT 且无法确认回滚时，才返回 `COMMIT_OUTCOME_UNKNOWN`；调用方继续按原 key 查询回执。非 SQLite 的业务或序列化异常也会清理本次事务。

## 内部调用结果

`UnitOfWork.did_commit` 在每次 `execute()` 开始时为 false；只有本次 COMMIT 成功返回后为 true，包含新提交的稳定拒绝。幂等重放和任何异常保持 false。该属性不进入 wire DTO，也不是持久执行租约。启动外部副作用的消费者必须同时满足 `did_commit` 与 `receipt.status == accepted`，并保留自己的持久启动意图及未知结果处理。

同一 UnitOfWork 实例重试前会清空上一轮审计缓冲，避免被回滚的事件混入后续成功事务。

## 验证

[新增回归](../../tests/p01_store/test_uow_replay.py) 18 项覆盖完整成功/拒绝回执重放、瞬态恢复、正常和拒绝路径的同 key / 异 hash 竞争、真实 SQLite busy、正常及拒绝提交体的确定失败、成功回滚与提交成功但确认丢失、序列化失败回滚、两线程同 key 仅一个提交者。

2026-10-09 使用项目 `.venv`、Python `-B`、`pytest -p no:cacheprovider` 和显式 OS temp `--basetemp` 运行 `tests/p01_store`：40 项通过，包含 CR-004 的独立连接并发序号回归。测试只创建隔离临时数据库；未运行全量测试、DSH 或 Git。失败注入使用临时 SQLite trigger 或测试连接代理，不改生产数据库。

## 边界

提交成功但调用方未得到确认仍需先查询回执，不能自动重做外部操作。此变更不为已有历史缺陷数据补写字段，不修改数据库结构，也不实现 DSH 接入。
