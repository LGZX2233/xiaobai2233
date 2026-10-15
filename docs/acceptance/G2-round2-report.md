# G2 第二轮内核整改报告

日期：2026-10-09。范围：D:/deepseekhannes/kernel_next。结论：第二轮整改已集成，528 项 Python 联合测试、2 项追加验收回归和 14 项 Node 测试通过；本轮身份、数据证据、项目绑定与旧数据入口问题已独立复验关闭。G2 整体保持待验收，不签发生产或宿主适配放行回执。

## 交付

| 模块 | 当前行为 | 复核依据 |
| --- | --- | --- |
| 项目身份 | 独立身份入口创建/对账项目，持久身份域回执；校验项目唯一 stamp、迁移、manifest 和 Windows 路径；活动项目丢库时不重建空库 | [身份审查](../reviews/2026-10-09-round2/identity-review.md) |
| 项目绑定 | 仅配置 identity_registry 时在项目入口声明；项目意图、身份结果、项目结算分别持久化，重启沿原回执恢复；最大合法幂等键可结算 | [绑定与导入审查](../reviews/2026-10-09-round2/project-legacy-review.md) |
| 旧数据入口 | test 模式显式配置 snapshot provider 和可信来源后开放；精确快照、计划与摘要核验；事实、隔离项和回执同事务；同键重启不重复导入 | [来源交接](../handoffs/round2-source-recovery.md) |
| 来源完整性 | 来源身份使用无歧义元组编码，缺口样本和区间有界；旧歧义游标标为不可确认；principal、provider 与执行模式必须一致 | [数据证据审查](../reviews/2026-10-09-round2/data-evidence-review.md) |
| 证据与环境提供者 | 应用层通过内部端口调用文件、备份、恢复、归档和环境提供者；提供者原始结果保留，不能覆盖固定项目、任务和操作关联 | [提供者交接](../handoffs/round2-provider-separation.md) |
| 历史与归档 | 阻塞打开/解决追加 revision，历史查询按水位重建；归档精确版本不读取未来回执；成功需对应清单摘要与验证标记；缺必需回执为 pending | [查询和归档审查](../reviews/2026-10-09-round2/data-evidence-review.md) |
| 交付与存储 | 对账核验操作、目标摘要、制品字节和精确 fence；非布尔终态不证明效果结束；不支持的库版本拒绝打开，初始化异常释放资源 | [变更记录 CR-009](../changes/CR-009-kernel-boundaries.md) |

执行流可以更新项目数据；事实和审计独立留存。重放回执不等于重做外部效果，未知结果继续保留为未知。可选知识与语料出口保持默认关闭。

## 验证与留档

联合测试最终为 528 passed、0 failed；追加精确冻结引用及公开分页回归 2 passed，合计 530 项互不重复的 Python 测试；Node 14 passed、0 failed。冻结契约摘要保持 d5fe5816356b0731e78790e997857ea18668cbec16f68673da1f433da07c97cc。子集复跑与独立审查数字不叠加到联合测试总数。

- [机器状态](G2-round2/status.json)、[检查映射](G2-round2/checks.json)、[实际命令](G2-round2/commands.md)。
- [原始联合 JUnit](G2-round2/evidence/pytest-final.xml)、[Node 原始输出](G2-round2/evidence/node-tests.txt)、[失败与修复记录](G2-round2/failures/repair-history.md)。
- [源码与证据哈希清单](G2-round2/artifact-manifest.json)。该清单属于本轮，不覆盖前轮指纹。
- [前轮报告快照](G2/round1-metadata/G2-report.md) 与原 G2/evidence 保留。临时补丁不进入知识库，合成场景和探针单独标为 test。

[原评审逐项复验](../reviews/2026-10-09-round2/original-findings-revalidation.md) 独立运行 96 项；[场景与恢复审查](../reviews/2026-10-09-round2/scenario-recovery-review.md) 独立运行 5 项，并检查实际数据库、制品和审计内容。新增两项验收证据由主集成者再次复跑。以上重叠复跑均不另计测试总数。

独立审查发现 IR-01 至 IR-09、DE-01 至 DE-05、PL-01，修复后均由非该项实施者复验。本条说明已覆盖范围，不把局部签字扩写成整体 G2 接受。

## 下一轮入口

先按 [实施与复验计划](../plans/2026-10-09-kernel-remediation-next.md) 完成剩余交付提供者分离、恢复/对账调度和 G2 逐项裁决，再进入可选知识能力及 DSH 离线适配设计。真实 DSH flush、操作系统沙盒、人类身份、生产恢复、界面和 Git 尚未验收，详见 [限制](G2-round2/limitations.md)。

本轮没有修改 DSH 包、旧内核或冻结设计，没有调用付费模型、恢复生产库、训练、上传或对外分发数据。
