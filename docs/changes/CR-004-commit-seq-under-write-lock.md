# CR-004：commit_seq 必须在写锁内分配（P01 Store/UoW）

- 提出者：P13（集成验收）
- 目标 owner：P01（`src/project_kernel/data/store/uow.py`、`store.py`）
- 关联：AC07/AC08（短 UoW、CAS、幂等）、AC45（并发/资源卫生）、G2 报告 §4.6「多线程真并发 stress」
- 结论：**已由 P13 直接修复并加回归测试**（owner 不在线，缺陷会导致假失败与水位碰撞，
  属集成阻断级；修复面极小且不改任何契约/DDL/公共 DTO）

## 1. 现象

P03/P13 真并发 stress（4 个真实线程 + 真实 subprocess provider、同一项目库不同连接）暴露出：

```
KernelError: COMMIT_OUTCOME_UNKNOWN: Commit outcome unknown; query command.receipt with the original key
  cause: sqlite3.IntegrityError: UNIQUE constraint failed: commit_log.commit_seq
```

同时 `ThreadPoolExecutor + barrier` 的写法在 worker 先失败时会整体死锁（本地两次死机即由此放大），
该测试写法已同步修正为显式线程 + 有界等待 + 失败即 abort。

## 2. 根因

`UnitOfWork.execute()` 在 `BEGIN IMMEDIATE` **之前**调用 `store.next_commit_seq()`：

```python
commit_seq = self.store.next_commit_seq()   # SELECT MAX(commit_seq)+1，未持写锁
...
conn.execute("BEGIN IMMEDIATE")
```

两个写者的读发生在各自的事务外，可以取到同一个 `commit_seq`；第二个写者在
`_write_commit()` 的 `INSERT INTO commit_log` 撞 UNIQUE 约束，被 `except sqlite3.Error`
映射成 `COMMIT_OUTCOME_UNKNOWN`。这是**假失败**：命令根本没提交，客户端却拿到「结果未知」，
并且设计要求的「BEGIN IMMEDIATE 单写者」保证被读-写窗口破坏。`_commit_rejection()` 同样在
事务外取序号。

## 3. 修复

`uow.py`：把 `commit_seq` 的分配移入 `BEGIN IMMEDIATE` 之后（`Records`/`Outbox`/`SourceIngest`
的构造也随之移到锁内），`_commit_rejection()` 亦同。行为不变：一次事务仍只有一个 commit_seq、
一个 command_id、一个 receipt；只是序号分配在写锁保护下完成。

```python
conn.execute("BEGIN IMMEDIATE")
try:
    dup = self._check_idempotency()
    if dup is not None:
        conn.execute("ROLLBACK"); return dup
    # Allocated while holding the write lock: a read outside the
    # transaction lets two writers publish the same commit_seq.
    commit_seq = self.store.next_commit_seq()
    handles = Handles(records=Records(conn, ..., commit_seq, command_id, principal), ...)
    callback(handles)
```

## 4. 证据

- 回归测试 `tests/p01_store/test_concurrency.py::test_concurrent_writers_never_collide_on_commit_seq`
  （真实线程、独立连接、`commit_seq` 必须是 1..N 无重复无空洞）。
- 反向验证：临时还原旧顺序后该测试**失败**（`AssertionError`），恢复修复后通过；文件恢复前后
  sha256 一致。
- `tests/p01_store`、`tests/p03_attempt` 全绿；全量见 G2 报告。

## 5. 未变的边界

未改 `contracts/`、schema/DDL、公共 DTO、错误码；`store.next_commit_seq()` 语义（当前水位读）
保留，供只读水位查询使用。仍待后续（P01 owner 决定）：是否把 `commit_seq` 迁移为
DB 自增/序列表以获得更强保证；本回合以写锁内分配满足单写者语义。
