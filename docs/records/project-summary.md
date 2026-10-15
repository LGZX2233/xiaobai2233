---
record_id: CCR-PROJECT
record_version: 13
updated_at: 2026-10-15
timezone: Asia/Shanghai
source_revision: 16410c9fbf4a8507445b4603e371e701614e4499
source_worktree: consumer, SCM, training, skill and kernel design documentation; runtime unchanged
status: active
requirement_ids: [REQ-BOUNDARY-01, REQ-BOUNDARY-02, REQ-BOUNDARY-03, REQ-BOUNDARY-04, REQ-BOUNDARY-05, REQ-BOUNDARY-06, REQ-BOUNDARY-07, REQ-BOUNDARY-08, REQ-BOUNDARY-09, REQ-BOUNDARY-10, REQ-BOUNDARY-11, REQ-BOUNDARY-12, REQ-BOUNDARY-13, REQ-CCR-05, REQ-CCR-10, REQ-SG-01, REQ-SG-02, REQ-SG-03, REQ-SG-04, REQ-SG-05, REQ-SG-06, REQ-SG-07, REQ-RPC-01, REQ-RPC-02, REQ-RPC-03, REQ-RPC-04, REQ-RPC-05]
module_ids: [K-RECORDS, K-RPC, K-ROOT, K-QUERIES, K-KNOWLEDGE, K-DELIVERY, K-CORPUS, K-EXECUTION, K-STORAGE, K-LEDGER, K-DESIGN]
acceptance_status: not_behaviorally_validated
---

# 内核项目总结

Project Kernel 保存需求、方案、尝试、验收、审批、交付和证据之间的精确关联，支持查询项目进展与追溯来源。它由宿主组合和调用；真实 DSH 适配与工作台分别属于 G3、G4，不由独立核心的接受结果代替。

## 当前事实入口

| 主题 | 当前摘要 | 主记录 |
| --- | --- | --- |
| 目标与结构 | 执行流、项目数据、纯领域规则和显式 provider 组合；维护目标是保持内核干净、职责清晰 | [架构](../architecture/kernel-architecture.md)、[模块树](../modules/README.md) |
| 完整设计与成长路线 | 八阶段执行闭环、L0/L1、模型输出垃圾治理、低耦合边界和无可视化 agent 接入计划 | [设计与成长](../architecture/kernel-design-and-growth.md)、[本次任务](tasks/2026-10-15-kernel-cleanup.md) |
| 独立核心接受 | 冻结25项87条件为 `accepted_g2`；`release_approved=false` | [G2 第四轮报告](../acceptance/G2-round4-report.md)、[条件与证据](../acceptance/G2-round4/checks.json) |
| 当前能力 | 显式组合、版本账本、执行和交付事实、来源证据、查询、test 范围恢复 | [内核现状](../architecture/current-state.md) |
| RPC 修复与剩余问题 | RPC 深度、Unicode/id 和序列化兜底修复已提交并推送 main，仅静态审查、未行为验证；knowledge 提升缺口仍未修复，且未接入核心 RPC | [RPC 修复记录](tasks/2026-10-10-rpc-resilience.md)、[静态设计审查](../reviews/2026-10-10-design-review.md) |
| 记录与学习 | 模块树、项目/任务总结、学习资料与文字画像帮助查找和理解项目 | [记录目录](README.md)、[持续记录职责](../architecture/continuous-records.md) |
| 技能成长 | 在项目内改进可复用工作方法；技能评价与用户画像分开 | [技能成长](../architecture/skill-growth.md)、[当前需求](../requirements/2026-10-10-clean-layout-and-skill-growth.md) |
| 目录整理 | 测试集中在 tests，运行源码缓存已清理；原验收保留原路径与字节摘要 | [目录分工](../development/repository-layout.md)、[当前任务](tasks/2026-10-10-layout-and-skill-growth.md) |

## 必须保留的设计约束

业务事实使用不可变版本和精确引用；写入使用幂等回执和当前版本核验。未知外部效果保持 unknown，通过观察或显式对账处理。文档摘要、用户画像和插件规则不授予审批权限，不删除失败历史，不把 test 证据升级为 production。

模块树是文档导航，业务账本仍由运行内核拥有。记录维护跟随每次工作，来源、版本、撤回和删除规则见[持续记录架构](../architecture/continuous-records.md)，具体规则扩展以相关主文档为准。

## 当前限制与维护方向

运行仍依赖完整源码树中的 `contracts/v1`，尚无已接受的独立 wheel 部署方式。knowledge 未接入核心 RPC，corpus 默认关闭，恢复只开放指定 test 范围。记录及 skill 由当前 Codex 工作流使用，尚无内核自动同步或学习画像运行服务。模型输出的 staging/manifest/digest/批准闭环已有基础，但 output kind/路径预算、quarantine 扫描、自动引用检查和 OS 级沙盒仍待实现；无可视化 agent 接入处于 H0-H2 计划阶段。

[RPC 修复](tasks/2026-10-10-rpc-resilience.md)及前期维护已普通提交并推送 main；修复源码是 `c364539`，随后同步资料以 `62bb5d7` 交付。具体远端回执与读取结果见[同步记录](../handoffs/2026-10-10-rpc-fix-main-sync.md)。[README](../../README.md)现按项目用途、当前进度、能力与阅读入口介绍内核；本次描述修订不改变运行源码。原发现与 knowledge 开放条件见[静态设计审查](../reviews/2026-10-10-design-review.md)和[后续计划](../plans/2026-10-09-kernel-remediation-next.md)。[布局与技能成长任务](tasks/2026-10-10-layout-and-skill-growth.md)及[原内核维护任务](tasks/2026-10-10-kernel-maintenance.md)保留各自阶段的建立记录。

用户知识熟悉程度尚未知。技术路线说明可依据其明确需求强调模块入口、来源追溯和渐进解释，不应据此推断其 Python、Node、数据库或图结构能力；详细描述由[用户学习画像](user-learning-profile.md)拥有。

## 来源

当前修复源码依据是顶部 `source_revision`；原审查保留修复前版本。G2 仓库同步的历史事实见[原远端同步记录](../handoffs/2026-10-10-g2-acceptance-remote-sync.md)，RPC 修复及维护的普通主分支推送见[当前同步记录](../handoffs/2026-10-10-rpc-fix-main-sync.md)。摘要不会接管冻结验收或既有证据。

## 修订记录

| 记录版本 | 更新时间 | 内容 |
| --- | --- | --- |
| 1 | 2026-10-10 | 建立带精确源码版本和当前维护限制的项目摘要；引用原 G2 接受与静态问题主记录 |
| 2 | 2026-10-10 | 按能力、限制和阅读入口组织当前摘要，加入技能成长与当前任务链接 |
| 3 | 2026-10-10 | 关联 RPC 修复要求、仅静态审查状态及当前主分支同步授权 |
| 4 | 2026-10-10 | 记录已提交修复源码与普通 main 同步结果 |
| 5 | 2026-10-10 | 补齐 README 当前描述及62bb5d7文档交付，远端重新读取成功 |
| 6 | 2026-10-12 | 新增消费者、SCM、训练及 skill 范围说明，静态复核纠正旧评价 |
| 7 | 2026-10-12 | 记录已选路线 A 与项目/模块双层存储分工，多代理文档校准与独立复核 |
| 8 | 2026-10-12 | 记录 R1 从零复现总指南与四章参考规格，明确用户决定与 R1 实现选择分界 |
| 9 | 2026-10-13 | 同日会话总结：确认执行流与双层存储思路，归档未决项，无新实现或验收 |
| 10 | 2026-10-13 | 完成 R1 设计评价：确认不变式/六层完成分层为最强部分；钉死 host_work 归属、表单暂态、问答唤醒、评分防混、计量模式与并发增长验收六项前置，见 R1 设计评价与任务记录 |
| 11 | 2026-10-13 | 记录 AGH 独立适配及既有检查，详情由当时任务拥有 |
| 12 | 2026-10-15 | 新增完整设计与治理/成长路线入口 |
| 13 | 2026-10-15 | 重写内核 README、整合设计与问题映射、记录持续整洁/headless 计划及视频成果 |

## 2026-10-12 当前补充

[架构边界与评价核对](tasks/2026-10-12-kernel-boundaries.md)记录本次文档交付、静态核对和未完成范围。消费者权威视图读已提交事实；SCM 仍是待设计接入；corpus 已有候选样本/审核/切分，但默认关闭。评分与失败总结只有数据处理用途，不接入执行；发布状态与真实宿主验证缺口不变。

记录版本 6：新增消费者、SCM、训练及 skill 范围说明，静态复核纠正旧评价；没有运行接线或行为验证。

记录版本 7：[模型收尾采用路线 A](../architecture/model-review-identity.md)，模型提供方案评分、审阅与整理建议，人类确认固定方案包及依据的正式纳入。项目/模块架构需求、过程留存与正式收敛的分工见[双层存储](../architecture/dual-layer-storage.md)。按用户要求分发三名代理实施文档校准并独立复核；多层分支嵌套仍待决定，新增运行能力仍未实现或验收。

记录版本 8：[从零复现总指南](../architecture/reproduction-blueprint.md)及四章 R1 规格提供字段、事务、状态、上下文、模型调用、评分、人工采用、恢复、实施顺序与验收图表。继续同轮多代理编写，R1 新接口仅为参考设计；没有实现运行能力或新增接受，检查及代理故障见同一任务记录。

记录版本 9（2026-10-13）：同一会话继续执行流与存储分层总结。用户确认的整体思路与既有 R1 规格一致：设计模型主动讨论技术方案与需求理解，分发并行执行，执行在沙盒处理，任务表单通讯验收，多实现方案包评分提交（未采用也可留存），收尾验收并入主库并整理模块耦合；数据存储分项目整体（L0）与模块独立（L1）两套架构与需求，L1 主要供执行流阅读；实时表单归编排层、可溯源智能体交换归内核（`model_exchange` 候选）；设计侧主动表述固定为 REQ-BOUNDARY-12 常设要求。新增未决项按既有文档纪律记录：L1 物理形态（同库分区或独立库）、多层分支嵌套、收敛命令 schema/幂等、耦合度量首版范围、`model_exchange` schema 均待设计；以上均无实现或行为验收，`release_approved=false` 不变。主记录见[需求](../requirements/2026-10-12-kernel-boundaries.md)、[任务](tasks/2026-10-12-kernel-boundaries.md)与[R1 总指南](../architecture/reproduction-blueprint.md)。

记录版本 10（2026-10-13）：完成 [R1 设计评价](../reviews/2026-10-13-r1-design-review.md)。确认 12 不变式、六层完成分层与 R1/v1 显式隔离为设计最强部分；提出六项实施前置：host_work 移出内核 DDL（宿主自管队列、内核只留不可变审计事件）、表单暂态生命周期、model_exchange 唤醒机制、评分三套 schema 防混、exact 计量 provider capability 声明、并发增长验收项。修订 01/02/03 章后再按 S0→S7 分发实施；无实现或行为验收，`release_approved=false` 不变。

记录版本 11（2026-10-13）：[AGH 只读前端接入](tasks/2026-10-13-agh-frontend.md) 按用户要求分发三个代理实施，校对真实 RPC、保留查询信封及历史水位，增加总览与九个指定视图。隔离 AGH 实例已完成安装、信任、启用并运行；p15/p14 共 5 项通过，浏览器检查通过。未改日常实例、AGH 源码或历史 G2 接受，`release_approved=false` 不变；活动会话限制由任务记录拥有。

记录版本 12（2026-10-15）：新增[内核设计、问题治理与无界面接入计划](../architecture/kernel-design-and-growth.md)，明确模型输出治理、模块边界与无 UI agent 路线。

记录版本 13（2026-10-15）：README 聚焦独立内核，整合设计图、问题映射和实现边界；19 张图、3分53秒成片以及目录审计归于[本轮任务](tasks/2026-10-15-kernel-cleanup.md)。模型无主输出治理、模块耦合整改和 headless H0–H5 均为计划，未改内核运行源码或历史接受。
