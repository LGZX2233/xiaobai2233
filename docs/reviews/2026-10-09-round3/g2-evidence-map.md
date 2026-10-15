# G2 第三轮证据映射

日期：2026-10-09（Asia/Shanghai）。本表索引冻结 G2 范围 AC12–32、AC37–38、AC43、AC45 的公开入口和测试位置；不把测试文件存在或历史通过数量当作当前签字。本轮 555 项 Python 联合回归及 14 项 Node 协议测试通过，精确测试名与 JUnit 对应关系见[机器检查表](../../acceptance/G2-round3/checks.json)。命令、退出码、原始输出和源码摘要由[第三轮报告](../../acceptance/G2-round3-report.md)列明。当前总状态保持 `pending_g2_acceptance`。

冻结口径来自只读的 `D:/deepseekhannes/kernel/design-v1-20261008/acceptance-matrix.json` 与 `07-验收与迁移发布.md`。公开 machine 入口由 [`bootstrap.py`](../../../src/project_kernel/bootstrap.py) 的 `MACHINE_COMMANDS` 提供；人工决定只由 `build_human_server` 的可信入口提供。每一项仍需要组合根结果、证据摘要和独立裁决。

| AC | 冻结场景 | 公开入口 / 证据位置 | 当前索引判断与限制 |
| --- | --- | --- | --- |
| AC12 | 版本派发 | `dispatch.draft` / `dispatch.confirm`; [`tests/p02_design/test_design.py`](../../../tests/p02_design/test_design.py) | 可做模块证据；需当前组合根合法 payload 和冻结 packet 结果 |
| AC13 | 规则与未知 | `rules.save` / `rules.preview` / `rules.publish`; [`tests/p02_design/test_rules.py`](../../../tests/p02_design/test_rules.py) | 规则未知/拒绝有测试；生产事实 provider 仍未验收 |
| AC14 | 无 provider / 模拟 | `attempt.start` / `verification.run`; [`tests/p03_attempt/test_attempt.py`](../../../tests/p03_attempt/test_attempt.py), [`tests/p04_delivery/test_verification.py`](../../../tests/p04_delivery/test_verification.py) | 能力缺失和 simulation 语义需用当前组合根复验 |
| AC15 | 方案隔离 | `attempt.start` / `attempts.compare`; [`tests/p03_attempt/test_replay_regressions.py`](../../../tests/p03_attempt/test_replay_regressions.py), [`tests/p13_integration/test_closed_loop.py`](../../../tests/p13_integration/test_closed_loop.py) | test executor 闭环；需保留 A/B scope 与 strategy root 产物 |
| AC16 | 取消与重试 | `attempt.cancel` / `attempt.start` / `operation.status`; [`tests/p03_attempt/test_replay_regressions.py`](../../../tests/p03_attempt/test_replay_regressions.py) | unknown cancel 与新 attempt 有回归；宿主真实取消属于 G3 |
| AC17 | 环境真实结果 | `environment.probe` / `environment.report`; [`tests/p05_evidence/test_service.py`](../../../tests/p05_evidence/test_service.py) | 当前为本地 Python 探测；无宿主 provider 矩阵 |
| AC18 | 验收归属 | `verification.run` / `operation.status`; [`tests/p04_delivery/test_verification.py`](../../../tests/p04_delivery/test_verification.py) | zero/skipped/unknown/stale 规则有测试；需当前 candidate digest 证据 |
| AC19 | 申请状态 | `delivery.request` / `approvals.queue`; [`tests/p13_integration/test_closed_loop.py`](../../../tests/p13_integration/test_closed_loop.py) | 申请不自动批准；需公开入口回执和 approval revision |
| AC20 | 可信 human | `approval.decide`（human entry）; [`tests/p13_integration/test_context.py`](../../../tests/p13_integration/test_context.py), [`tests/p13_integration/test_wiring.py`](../../../tests/p13_integration/test_wiring.py) | 仅 synthetic interaction proof；真实宿主身份属于 G3/G4 |
| AC21 | 失效准确 | `approval.decide` / `approval.revoke`; [`tests/p04_delivery/test_approval.py`](../../../tests/p04_delivery/test_approval.py) | decisive 与无关输入已有回归；需当前快照摘要 |
| AC22 | 无循环 hash | `delivery.request` / `archive.export`; [`tests/p04_delivery/test_delivery.py`](../../../tests/p04_delivery/test_delivery.py) | snapshot digest 测试；需当前 manifest 产物摘要 |
| AC23 | claim 崩溃 | `delivery.apply` / `delivery.reconcile` / `operation.status`; [`tests/p04_delivery/test_reconcile.py`](../../../tests/p04_delivery/test_reconcile.py), [`tests/p04_delivery/test_effect_regressions.py`](../../../tests/p04_delivery/test_effect_regressions.py), [`tests/p04_delivery/test_provider_recovery.py`](../../../tests/p04_delivery/test_provider_recovery.py) | 本轮已重跑；观察失败、目标改变与重启后对账不可重写 sink |
| AC24 | fencing / 撤回 | `delivery.reconcile` / `approval.revoke`; [`tests/p04_delivery/test_reconcile.py`](../../../tests/p04_delivery/test_reconcile.py), [`tests/p04_delivery/test_approval.py`](../../../tests/p04_delivery/test_approval.py) | epoch 与无 fence unknown 有回归；需当前 provider receipt |
| AC25 | 真实 bundle | `delivery.apply` / `archive.export`; [`tests/p05_evidence/test_evidence.py`](../../../tests/p05_evidence/test_evidence.py), [`tests/p13_integration/test_closed_loop.py`](../../../tests/p13_integration/test_closed_loop.py) | 文件 provider 可测；非文件 sink 不在本轮 G2 要求 |
| AC26 | artifact 缺失 | `artifact.register` / `delivery.request`; [`tests/p05_evidence/test_evidence.py`](../../../tests/p05_evidence/test_evidence.py), [`tests/p13_integration/test_wiring.py`](../../../tests/p13_integration/test_wiring.py) | 缺失和摘要变更阻断 freeze；需当前产物清单 |
| AC27 | 并发 close / repair | `task.close` / `archive.repair`; [`tests/p04_delivery/test_effect_regressions.py`](../../../tests/p04_delivery/test_effect_regressions.py), [`tests/p05_evidence/test_service.py`](../../../tests/p05_evidence/test_service.py) | CAS 与 repair 规则有测试；需并发原始输出 |
| AC28 | 分 sink 故障 | `archive.export` / `archive.status`; [`tests/p04_delivery/test_closure.py`](../../../tests/p04_delivery/test_closure.py), [`tests/p05_evidence/test_service.py`](../../../tests/p05_evidence/test_service.py) | sink/source flush 分开；没有远端 final flush 证明 |
| AC29 | WAL 备份恢复 | `backup.create` / `restore.plan` / `restore.apply`; [`tests/p05_evidence/test_controlled_recovery.py`](../../../tests/p05_evidence/test_controlled_recovery.py), [`tests/p05_evidence/test_evidence.py`](../../../tests/p05_evidence/test_evidence.py) | 仅显式临时 test store；生产恢复后置 |
| AC30 | 覆盖 / 追溯 | `requirements.coverage` / `project.trace`; [`tests/p06_queries/test_graph_coverage.py`](../../../tests/p06_queries/test_graph_coverage.py) | 图查询测试；需当前读模型结果 |
| AC31 | 读水位统计 | `project.overview` / `project.timeline` / `events.read`; [`tests/p06_queries/test_readmodels.py`](../../../tests/p06_queries/test_readmodels.py), [`tests/p06_queries/test_typed_reads.py`](../../../tests/p06_queries/test_typed_reads.py) | watermarks 和 unavailable 语义有测试；需当前 as-of 输出 |
| AC32 | 迁移只读 | `legacy.import`（仅显式 test 配置）/ `project.timeline`; [`tests/p07_migration`](../../../tests/p07_migration) | synthetic immutable fixture；不读取生产数据 |
| AC37 | stdio 边界 | `initialize`, `kernel.command`, `kernel.query`; [`tests/p10_protocol`](../../../tests/p10_protocol), [`bridge/protocol/client_test.mjs`](../../../bridge/protocol/client_test.mjs) | 协议回归可索引；需第三轮 Node 原始输出 |
| AC38 | 超时重连 | `command.receipt` / `operation.status`; [`tests/p10_protocol/test_session_guards.py`](../../../tests/p10_protocol/test_session_guards.py), [`tests/p10_protocol/test_protocol.py`](../../../tests/p10_protocol/test_protocol.py) | receipt 重放和 unknown 语义；不证明宿主重启 |
| AC43 | 独立核心闭环 G2 | machine/human RPC 全链；[`tests/p13_integration/test_closed_loop.py`](../../../tests/p13_integration/test_closed_loop.py), [`tests/p05_evidence/test_controlled_recovery.py`](../../../tests/p05_evidence/test_controlled_recovery.py) | test 身份、`directory_only`、临时 subprocess；需 A/B、两方案、失败修复、人工批准、bundle、归档和总览的当前证据 |
| AC45 | 测试隔离 | `initialize` / `project.overview` / delivery queries; [`tests/p01_store/test_concurrency.py`](../../../tests/p01_store/test_concurrency.py), [`tests/p04_delivery/test_effect_regressions.py`](../../../tests/p04_delivery/test_effect_regressions.py) | 需第三轮明确 temp DB/WAL/SHM、产物与失败归档路径；缓存和运行数据库不得入库 |

## 裁决规则

通过必须同时有合法公开入口结果、与当前源码和 contract digest 对应的原始证据、以及独立逐项复核。单个模块测试、历史 Round 2 数字、空 payload 的 schema 拒绝、test 身份、`directory_only` 或 provider 能力声明都不能单独升级为 G2 通过。真实 DSH/Session/Jobs 属 G3，工作台属 G4，生产恢复及真实试点后置；它们不改变本表的 G2 范围。

未知效果、无法确认的来源 flush、未验证的人类身份和缺少历史事实必须保留其原状态或 `unavailable`。provider 观察异常归入 `unknown`，并且任何重放、查询或对账都不能再次执行外部写入。第三轮验收完成后，只能在 [`docs/acceptance/G2-round3/`](../../../docs/acceptance/G2-round3) 的状态、检查表和独立报告一致时更新结论。
