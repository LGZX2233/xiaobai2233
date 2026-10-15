# ChangeRequest 记录目录（P00 批准）

每个公共契约变更在此新增一个 Markdown 记录，字段：
问题描述、影响字段/语义、受影响消费者、迁移/测试、批准状态（P00 + P13）。

当前独立核心接受依据是[第四轮报告](../acceptance/G2-round4-report.md)，状态为 accepted_g2、release_approved=false。各 CR 正文保留实施当时的观察；本索引区分已纳入核心接受的整改和仍后置的能力，新增设计问题见[当前审查](../reviews/2026-10-10-design-review.md)。

[模块导航与持续记录要求](../requirements/2026-10-10-continuous-records.md)采用文档索引和项目 skill，不改变公共契约，故不新增契约 ChangeRequest；其交付及静态核对保存在[任务记录](../records/tasks/2026-10-10-kernel-maintenance.md)。

[测试布局与技能成长](../requirements/2026-10-10-clean-layout-and-skill-growth.md)继续保持公共契约不变，调整测试位置、方法指引和阅读入口；迁移与静态核对见[新任务](../records/tasks/2026-10-10-layout-and-skill-growth.md)，历史验收未重写。

## 现有记录

| 编号 | 主题 | 状态 |
| --- | --- | --- |
| CR-001 | 0002 领域表 DDL（P02/P04/P05/P06 索引表合入） | 已合入 |
| CR-002 | 旧库知识域 DDL（P07/P08 的 imported_fact / legacy_* / use_event / outcome / promotion_task） | 已合入（0003） |
| CR-003 | P08 四项 ChangeRequest 处置（含 shared 跨库复制后置） | 部分后置 |
| CR-004 | commit_seq 必须在写锁内分配（P01 缺陷修复） | 已修复并接受 |
| CR-005 | attempt 结算/取消保留 task/packet/strategy 关联（P03 缺陷修复） | 已修复并接受 |
| CR-006 | 组合根接线、`decision.record` 与 AC26 冻结门（跨 owner，P13 代行） | 历史记录；当前核心结论以第四轮裁决为准 |
| [CR-007](CR-007-uow-replay.md) | UoW 幂等回执与事务错误分类 | 相关核心行为已纳入第四轮独立接受 |
| [CR-008](CR-008-g2-remediation.md) | 权限、冻结输入、效果幂等、公开入口与受控恢复 | 相关核心整改已纳入第四轮；恢复仍限定 test stores |
| [CR-009](CR-009-kernel-boundaries.md) | 身份回执增量迁移、提供者拆分、来源授权与历史留档 | 相关核心整改已纳入第四轮；后置宿主能力不在接受范围 |
| [CR-010](CR-010-delivery-provider.md) | 交付 provider 显式装配、非文件 sink 与未知效果恢复 | 核心已独立接受；不声明 Git provider 或生产部署 |
| [CR-011](CR-011-g2-independent-acceptance.md) | 逐项独立 G2 入口证据、目录隔离、模式校验、批准失效、归档与协议整改 | 25项87条件 accepted，AC45 已独立签字 |

冻结 wire 契约、项目 DDL、公共 DTO 和错误码不变；CR-009 新增独立的身份命令回执迁移，不修改已有迁移；
`compute_bundle_digest()` 仍为 `d5fe5816356b0731e78790e997857ea18668cbec16f68673da1f433da07c97cc`。
