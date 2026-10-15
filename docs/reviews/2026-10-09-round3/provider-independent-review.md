# Provider 独立审查

日期：2026-10-09（Asia/Shanghai）。审查范围是当前工作副本的交付 provider 组合根、文件实现、非文件 provider 回归、RPC 接线、第三轮证据，以及冻结 G2 范围。审查没有修改源码、测试、冻结设计或既有证据；本文件是本轮唯一新增审查文件。

## 独立结论

本轮 provider 拆分后的交付路径具备可核查的授权、目标匹配、不可变 manifest、效果观察、未知状态和重放保护。没有发现会把观察失败当成成功、把目标变更当成原目标、或在查询/对账时再次执行外部写入的已确认缺陷。整体 G2 仍为 `pending_g2_acceptance`：当前证据支持 provider 收口范围，不等于冻结 AC12–32、AC37–38、AC43、AC45 已逐项签发，也不等于真实 DSH、工作台或生产恢复验收完成。

## 代码核对

- `bootstrap.py` 的 `KernelServices`、machine server 和 human server 都通过显式 `delivery_provider=` 装配；`bundle_exporter=` 只用于创建文件 provider，二者同时配置直接报错，二者都缺失时 delivery apply 在能力层拒绝。
- `DeliveryService` 在 claim、apply-start、settle 和 reconcile 前重新解析冻结 `delivery_target`，校验项目内 revision、digest、sink 集合及 provider 的 `target_matches`。重启后 provider 的 namespace 或 sink 集合变化会使观察保持 `unknown`，不会查询新目标或生成新写入。
- provider `apply()` 只在已批准、已 claim、已 apply-start 的操作上执行；`observe()` 单独读取效果。观察异常、非法 operation/status、错误 digest、非布尔终态或没有 fence 的 `absent_final` 都被规范化为 `unknown`。已有 sink receipt、command receipt 和 blocker 保留。
- 幂等 key 返回原 operation receipt；terminal operation 的 reconcile 是 no-op。settlement 丢失后通过 provider 查询恢复，不调用第二次 apply。文件 provider 对相同 manifest 重用并校验已有 bundle，对不同 digest 拒绝覆盖；repair 只补同一 manifest 的缺失或损坏文件。
- 文件 provider 的 `observe()` 通过冻结 manifest 和导出目录的 digest/文件校验确认 `applied`，目标缺失或校验异常不会自行修复或宣称最终无效果。

## 独立测试与证据

本审查单独运行：

```text
.venv/Scripts/python.exe -X utf8 -B -m pytest tests/p04_delivery/test_provider_recovery.py tests/p13_integration/test_delivery_provider_rpc.py -p no:cacheprovider --tb=short --basetemp=.validation-tmp/review-unique-provider-20261009 --junitxml=.validation-tmp/review-unique-provider-20261009/review.xml
```

结果：17 passed in 1.95s。第一次在受限沙盒中写入该临时 JUnit 目录时被 Windows 权限拒绝；使用相同命令在主机权限下重试通过。该权限问题不是产品测试失败。

第三轮最终证据复核：

- `docs/acceptance/G2-round3/evidence/python-verified-result.json` 的命令在当前源码上执行 `tests`，退出码 0；输出为 `555 passed in 23.95s`。
- `pytest-verified.xml` 共 555 个 testcase，按 `classname::name` 去重后仍为 555，失败 0、error 0、skipped 0。provider recovery、RPC memory delivery、双项目闭环、受控恢复和证据捕获校验用例均在其中。
- `docs/acceptance/G2-round3/evidence/node-verified-result.json` 记录 Node 协议测试退出码 0；输出为 14 tests、14 pass、0 fail、0 skipped。
- Python 和 Node verified 输出的 sha256 均与各自结果 JSON 相符；两份最终 capture 都登记运行前后输入未变，其各自 204 个源码、contract 和测试校验文件均存在且当前哈希一致。验证工具的 8 项新增正反回归覆盖失败退出码、输出陈旧、输入陈旧、缺少稳定指纹、越界输出路径和越界输入路径；对应 8 个 testcase 均在 JUnit 中通过。
- `pytest-final.xml`/`python-all-result.json` 的 545 项以及 `pytest-current.xml`/`python-final-result.json` 的 547 项属于较早中间快照；本审查采用 `pytest-verified.xml` 与 `python-verified-result.json` 的 555 项。provider 源码和 17 项独立 provider 范围未变。
- 实际读取 `.validation-tmp/round3-verified/test_dual_project_workflow_del0/scenario-evidence.json`，其中记录 3 次临时 subprocess 执行、3 次验收 provider 调用、保留的失败 attempt、旧新 approval、迁移源摘要和归档修复结果。该隔离目录内交付与归档两份 `manifest.json` 均存在，且各自所列 artifact 文件仍存在；运行数据库和这些临时文件不进入提交。

## G2 范围裁决

本轮可以接受 provider 收口相关的 AC23、AC24、AC25、AC27、AC28 证据增量，以及 AC43/AC45 中 provider、隔离、回执和恢复部分的当前测试证据。`g2-evidence-map.md` 仍正确保留限制：每项冻结标准还需要合法公开入口、当前源码/contract 对应的原始证据和独立逐项裁决；测试文件存在或总数通过不能替代签字。

AC43 仍应表述为 test 模式的隔离项目闭环，包含测试身份、`directory_only` 执行器、真实临时 subprocess、失败修复、人工批准、bundle、归档和总览；这不升级为真实 DSH 或生产宿主保证。AC29 的 WAL/恢复证据仍是显式临时 test store 与恢复 fence 演练。真实 DSH/Session/Jobs 属 G3，工作台属 G4，生产恢复及真实试点属后续部署阶段，不能直接作为 G2 阻断理由，也不能被本轮报告宣称已完成。

最终阶段口径：`pending_g2_acceptance`。后续签发前仍需保持当前证据与逐项检查表、状态、摘要清单一致，并明确记录剩余限制、Git 提交和远端同步结果。
