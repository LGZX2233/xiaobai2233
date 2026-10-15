# G2 第三轮内核整改报告

日期：2026-10-09（Asia/Shanghai）。范围仅 `D:/deepseekhannes/kernel_next`。交付 provider 装配、非文件 sink 与观察失败恢复已集成；当前代码通过 555 项不重复 Python 测试及 14 项 Node 协议测试。G2 保持 `pending_g2_acceptance`，未签发整体接受或生产放行。

## 当前交付

组合根接受显式 `delivery_provider=`，文件部署可用 `bundle_exporter=` 包装 `BundleDeliveryProvider`；两者同时配置立即报错，缺省不创建 provider。交付 manifest 和 `apply()` 的 sink 来自冻结目标，不再固定为 `exports`。应用层核验快照 body、目标精确版本和摘要；claim、apply-start 及恢复观察均要求当前 provider 匹配批准目标。

观察异常、非法操作身份或状态、错误摘要、非布尔终态及未证实的最终无效果均不能放行。结果保留 `unknown`、原 accepted command receipt、已有 sink receipt 和 blocker；诊断只保存异常类型。恢复、幂等重放、`operation.status` 和 `delivery.reconcile` 不重复 `apply()`。恢复后 provider 的 namespace 或 sink 范围改变时，不读取错误目的地；恢复原配置后可以只读对账结算。

非文件 provider 的合成服务/RPC 回归覆盖可信人工批准、跨项目拒绝、内存 sink 实际制品字节、未知观察、连接重启、回执查询及收尾。文件 provider 的现有回归覆盖真实 bundle、损坏制品、丢失结算、归档修复和受控 test-store 恢复。DSH 兼容层和工作台仍属于独立后续项目；目标用户知识树仅保留规划。

## 实际验证

| 范围 | 结果 | 原始证据 |
| --- | --- | --- |
| 当前完整 Python 测试 | 555 passed，0 failed/errors/skipped；23.95 秒 | [JUnit](G2-round3/evidence/pytest-verified.xml)、[输出](G2-round3/evidence/python-verified-output.txt)、[命令与指纹](G2-round3/evidence/python-verified-result.json) |
| provider 恢复子集 | 15 passed；包含两项恢复目标变更回归 | [JUnit](G2-round3/evidence/pytest-recovery-target.xml)、[命令](G2-round3/evidence/recovery-target-result.json) |
| Node 协议 | 14 passed，0 failed | [原始输出](G2-round3/evidence/node-verified-output.txt)、[命令](G2-round3/evidence/node-verified-result.json) |
| 独立 provider/RPC 复验 | 17 passed；与联合测试重叠，不另计总数 | [独立审查](../reviews/2026-10-09-round3/provider-independent-review.md) |

555 项包含第二轮现有用例、本轮 provider 回归和 8 项证据校验正反回归。旧 545 项运行早于最后一次恢复目标校验；547 项运行尚未包含校验工具测试，两者保留为中间结果。冻结契约摘要保持 `d5fe5816356b0731e78790e997857ea18668cbec16f68673da1f433da07c97cc`。源码/测试/协议文件运行前后指纹一致，子集复跑与独立复验不重复计数。

初次恢复子集在沙箱中因 pytest 私有临时目录 `WinError 5` 失败，原输出和 JUnit 在[失败目录](G2-round3/failures/recovery-target-sandbox)保留；原命令在获准的宿主权限下通过。第二轮 manifest 对当前源码的 hash mismatch 是历史快照变化的审计信号，旧 manifest 未重写。详见[实际命令](G2-round3/commands.md)。

## 验收与留档

[状态](G2-round3/status.json)、[25 项 G2 检查映射](G2-round3/checks.json)、[文件摘要清单](G2-round3/artifact-manifest.json)与[只读校验结果](G2-round3/verification-result.json)共同描述本轮。合成闭环摘要和临时产物 hash 单独标记 test；运行 DB/WAL/SHM、虚拟环境、缓存及凭证不进入提交，既有合成验收压缩包不修改。

映射已经关联当前 JUnit 中的实际测试名，仍须逐项确认冻结条件与公开入口产物是否充分，不能把所有文件里的测试通过直接扩写成全部 AC 独立接受。本轮独立审查只接受明确 provider 范围；后续裁决顺序见[计划](../plans/2026-10-09-kernel-remediation-next.md)与[完成交接](../handoffs/2026-10-09-provider-remediation-result.md)。

真实 DSH/Session/Jobs 属 G3，工作台属 G4，生产恢复及真实试点属于后续部署；它们没有作为 G2 直接阻断项。各平台当前仅“可适配”，会话、工具事件、取消、沙盒、身份、人审回调仍需逐宿主验收。其余部署限制见[本轮限制](G2-round3/limitations.md)。
