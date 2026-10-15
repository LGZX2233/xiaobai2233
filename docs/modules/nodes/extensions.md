# K-EXTENSIONS：可选能力与记录工作流

| 字段 | 值 |
| --- | --- |
| node_id | K-EXTENSIONS |
| node_kind | aggregate |
| document_version | 1.0.0 |
| updated_at | 2026-10-10（Asia/Shanghai，日期精度） |
| source_version | 1.0.0 |
| source_revision | `0a619766162682606ad57a9aa4c1926d54c1b891` |
| implementation_status | 可选/未接线能力与文档工作流分组 |
| navigation_parent | K-ROOT |
| conversation_refs | [] |

## 职责与入口

本分组导航到 test-only 迁移、未接线 knowledge、默认关闭 corpus 和持续记录工作流，不表示它们已经成为统一运行插件体系。[bootstrap.py](../../../src/project_kernel/bootstrap.py)的 `legacy_config` 与 `enable_corpus` 是可选配置；[knowledge](../../../src/project_kernel/knowledge/)是 library 实现；[维护 skill](../../../.agents/skills/kernel-maintain-records/SKILL.md)由 agent 工作流使用。

输入输出和存储方式各自不同：迁移与语料使用现有 Store，持续记录只维护版本化 Markdown。不能把用户画像存入 identity 表或让 skill 自动触发语料导出。

## 关系与记录

`depends_on=[]`，`related_to=[K-LEGACY, K-KNOWLEDGE, K-CORPUS, K-RECORDS]`。聚合关系仅用于导航。

| 来源 | 范围与状态 |
| --- | --- |
| [现状](../../architecture/current-state.md)、[原限制](../../acceptance/G2-round4/limitations.md) | test-only 迁移与可选知识/语料接受分别说明；G2-K 不能由 G2 自动放行 |
| [REQ-CCR-01/02/03/11](../../requirements/2026-10-10-continuous-records.md) | 保持新增资料集中、模块职责明确；本轮文档交付 |
| [知识提升问题](../../reviews/2026-10-10-design-review.md) | 未接线路径的授权和效果时序缺口仍保留 |

| 日期 | 文档版本 | 变更 |
| --- | --- | --- |
| 2026-10-10 | 1.0.0 | 区分运行可选能力和 agent 文档维护，未新增运行时 provider registry 或后台服务 |
