# G1 阶段验收报告（数据底座）

- 阶段门槛：G1 = data
- 日期：2026-10-08
- 冻结 contract bundle digest：`d5fe5816356b0731e78790e997857ea18668cbec16f68673da1f433da07c97cc`
- 状态：**G1 达成**（P01 owner 自检 + P13 集成检查均通过）

## 验收矩阵对照（AC04–AC11）

| AC | 场景 | 结果 |
| --- | --- | --- |
| AC04 | A/B 并发 scope、跨项目引用/空 scope 拒绝 | 通过（A/B 隔离 + 跨项目引用拒绝；空 scope 属 P02/P13 应用层） |
| AC05 | 初始化中断可 reconcile、binding 唯一、active 前禁写 | 通过（provision/reconcile/bind + require_active） |
| AC06 | 不可变 history：draft 不成 current、as_of 还原 | 通过 |
| AC07 | 事务故障：任一点异常全回滚 | 通过（RuntimeError 注入） |
| AC08 | 幂等与 CAS：同 key 重放/异 payload 拒绝/竞争单方推进 | 通过（BEGIN IMMEDIATE + CAS） |
| AC09 | 只读/迁移：ro 拒写、checksum 不符停启动 | 通过（只读拒写 + 迁移 checksum 校验） |
| AC10 | 来源重投乱序：连续 cursor 不跨 gap、冲突、去重 | 通过 |
| AC11 | outbox lease：旧 lease ACK 不覆盖新 owner | 通过 |

## 实际检查命令与结果

```
.venv\Scripts\python.exe -m pytest tests\p01_store -q   # 21 passed
.venv\Scripts\python.exe -m pytest tests -q             # 50 passed
```

## 备注

- 多线程真并发 stress 与领域表 DDL 合入留给 P02/P03/P04 提出需求后由 P01 追加迁移。
- 下一阶段：G2 波次（P04 纯 flow 先行 → P02/P03/P05/P06/P10 接入）。
