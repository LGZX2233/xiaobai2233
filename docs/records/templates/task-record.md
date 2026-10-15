---
record_id: CCR-TASK-TEMPLATE
record_version: 1
updated_at: 2026-10-10
timezone: Asia/Shanghai
source_revision: 0a619766162682606ad57a9aa4c1926d54c1b891
source_worktree: uncommitted maintenance documentation
status: template
requirement_ids: [REQ-CCR-04]
module_ids: [K-RECORDS]
acceptance_status: not_behaviorally_validated
---

# 任务记录模板

维护者创建新任务文件时替换以下字段和章节。模板自身没有执行结果；未知、为空和未验证是有效状态，不补造来源、接受、用户知识程度或 Git 提交。

```yaml
record_id: CCR-TASK-<稳定任务标识>
record_version: 1
updated_at: <实际更新日期>
timezone: <实际时区>
source_revision: <完整源码提交或 unknown>
source_worktree: <未提交范围或 clean>
status: in_progress
requirement_ids: []
module_ids: []
acceptance_status: not_behaviorally_validated
```

## 目标与范围

记录用户已授权目标、工作范围、排除项和本次验证要求。引用需求主记录，不在本页重新裁定需求状态。

## 输入与来源

列出实际源码版本、需求 ID、节点 ID、当前记录和必要的历史验收入口。多来源各写自己的版本；没有对话映射时不创建对话引用。

## 技术选择与结果

记录已采用选择、适用原因和实际产物。把已执行、静态判断、未实施和未验证分别表述；修复事项引用问题主记录。

## 错误与学习资料

记录实际问题、来源和处理状态。没有执行失败时明确静态发现；复用术语或学习资料，不从错误推断用户能力。

## 验收与限制

引用本次实际验证和接受依据，列出未验证事项。没有新接受时不继承历史接受；命令只记录实际运行结果。

## 交接与修订

记录下一步、依赖和仍需人工决定的事项。状态完成后更新实际日期和版本，追加简短修订行；删除信息时不在修订行重抄原内容。规则见[持续记录架构](../../architecture/continuous-records.md)。
