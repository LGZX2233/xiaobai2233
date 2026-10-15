---
record_id: SG-TASK-20261010
record_version: 2
updated_at: 2026-10-10
timezone: Asia/Shanghai
source_revision: 0a619766162682606ad57a9aa4c1926d54c1b891
source_worktree: uncommitted test relocation, documentation and project skill revisions
status: completed_maintenance
requirement_ids: [REQ-SG-01, REQ-SG-02, REQ-SG-03, REQ-SG-04, REQ-SG-05, REQ-SG-06, REQ-SG-07]
module_ids: [K-ROOT, K-BRIDGE, K-RECORDS]
acceptance_status: not_behaviorally_validated
---

# 2026-10-10 测试布局与技能成长

本次整理测试目录、技能适用与评价方法，以及面向用户的阅读入口。[需求记录](../../requirements/2026-10-10-clean-layout-and-skill-growth.md)保存七项要求；[原维护任务](2026-10-10-kernel-maintenance.md)保留模块树和持续记录建立时的结果。

## 结果与范围

三个子任务按用户指定采用 `gpt-6.1-sol`：测试布局、技能成长、用户文档。目录与文档工作不增加内核运行能力；用户“不用测试了”的要求继续有效，没有运行测试、行为探针或重建验收。

| 主题 | 实际结果 | 主入口 |
| --- | --- | --- |
| 测试布局 | 三个 Node 测试与 vectors 迁至 `tests/bridge/`；更新 Node imports 和 Python fixture 引用；Python 测试仍在原测试目录 | [目录分工及路径映射](../../development/repository-layout.md)、[测试目录](../../../tests/README.md) |
| 功能目录清理 | 删除 `src/project_kernel/` 内22个 `__pycache__` 目录、89个生成 `.pyc`；运行 `.py` 和 bridge 实现未改 | 本记录与目录分工 |
| 技能范围与成长 | 维护 skill 修订为2.0.0，新增成长 skill 1.0.0；记录版本范围、证据及四维评价、反例和复核链路 | [成长方法](../../architecture/skill-growth.md)、[技能索引](../skills/registry.json) |
| 真实反馈 | 用户指出评价闭环、适用判断和阅读体验需要改进；保留反馈及修订，分数均为 null，新版本仍待观察 | [复核记录](../skills/2026-10-10-maintain-records-review.md) |
| 阅读入口 | README、模块目录、记录目录、项目摘要、学习画像、学习资料及现状按阅读目标组织；详细元数据留在相应记录与节点 | [模块树](../../modules/README.md)、[项目总结](../project-summary.md) |

没有修改全局 `skill-creator`。它是用于编写 Codex skill 的创作指南，项目新增文件是 agent 工作流资料；未启用内核 knowledge、自动画像、自动技能晋升或运行时插件加载。

审批按实际操作及会话已有授权判断。普通项目文档维护已获授权，无需再问；skill 不授予发布、外部写入、数据删除或额外验证权限。内核原有可信人审与交付审批仍由运行内核负责。

## 静态核对

| 核对 | 实际结果 |
| --- | --- |
| Markdown | 55份变更及新增文档，648个本地目标、17个标题锚点有效；单一末尾换行及尾空白核对通过 |
| 节点与结构化索引 | 23节点、77条依赖、107条相关关系；文档与 JSON 一致，导航无环，关联目标存在，对话列表为空；25个原 AC 有节点入口 |
| Skill 索引与 frontmatter | 2个 skill 路径、当前版本及全部 review/evidence 引用存在，name/description/skill-version 静态一致；新版本仍为 trial/not_validated |
| 测试迁移 | 三个迁移文件分别通过 `node --check`；新引用目标存在；与 HEAD 原文件逐项比较，仅预期 import 和命令说明改变 |
| Python 引用 | 用 `.venv/Scripts/python.exe -B` 解析 `test_vectors.py` AST 通过；人工核对其 fixture 指向 `tests/bridge/vectors.json`，没有导入或运行测试模块 |
| 功能目录 | `src/project_kernel/` 仅92个 `.py` 文件，无缓存目录；`bridge/protocol/` 仅 client.mjs、canonicalize.mjs；运行实现 Git 差异为空 |
| 保护摘要 | 53项 protected-inputs 全部 SHA256 相同；历史原始证据、冻结资料及既有 ZIP 未改 |
| 历史 manifest | 共1281条，四个旧路径已迁移、六个既有文件摘要变化，其余记录存在且摘要一致；原 manifest 保留 |
| Git | `git diff --check` 通过；未提交、未推送，HEAD 仍为基准源码提交 |

没有重新运行标准 skill validator；此前环境缺少 PyYAML 的限制保留在原任务记录，本次没有安装依赖。语法和路径检查不证明行为通过，亦不作为技能复用成功分数。

## 历史证据与未解决问题

原 G2 状态为 `accepted_g2`，`release_approved=false`。测试搬迁后历史 manifest 的四个旧路径不再存在于工作树；原 manifest、签字和计数保留原样，新旧位置及字节变化另记。`vectors.json` 保留字节，三个 Node 测试仅调整引用和运行说明，Python fixture 消费端调整路径。

迁移后的 vectors SHA256 为 `e07ed7d73ff02d87cb173fc47af550cc47d38577fde5d50d5a2b06791d951049`，与 HEAD 原文件一致。六项既有摘要变化是 README、内核架构、changes 目录、两份计划及 `tests/p10_protocol/test_vectors.py`。这些变化不在53项保护输入中，未用新摘要覆盖历史值。

53项 protected-inputs、冻结契约、第三轮原始证据和既有 ZIP 保留。`.validation-tmp/pre-main-review/evidence` 的原始输出未删除；本次只清理功能源码中的生成缓存，不将含证据的目录整体删除。

[静态审查](../../reviews/2026-10-10-design-review.md)记录的 RPC 递归解析、Unicode 错误响应，以及未接线 knowledge 提升问题仍未修复。用户此前“没问题推主仓库”的条件尚未满足；本次没有提交或推送 main，当前 HEAD 仍为顶部源码提交。

以上是本次目录与文档交付结束时的状态。用户随后授权的 RPC 修复与提交由[后续任务](2026-10-10-rpc-resilience.md)拥有；当前代码和 Git 状态进入该任务核对，不把本页阶段结果当作后续尚未修复的结论。

## 修订记录

| 记录版本 | 日期 | 内容 |
| --- | --- | --- |
| 1 | 2026-10-10 | 建立获授权改进的产物和范围记录，等待整合静态核对 |
| 2 | 2026-10-10 | 整合静态核对通过，目录与文档维护完成；保留未验证技能、新旧路径差异及未修复核心问题 |
