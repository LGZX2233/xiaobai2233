# K-CORPUS：默认关闭的语料能力

| 字段 | 值 |
| --- | --- |
| node_id | K-CORPUS |
| node_kind | module |
| document_version | 1.1.0 |
| updated_at | 2026-10-12（Asia/Shanghai，日期精度） |
| source_version | 1.0.0 |
| source_revision | `16410c9fbf4a8507445b4603e371e701614e4499` |
| implementation_status | 已有可选实现，enable_corpus 默认 false；G2-K 待接受 |
| navigation_parent | K-EXTENSIONS |
| conversation_refs | [] |

## 职责与入口

[CorpusService](../../../src/project_kernel/corpus/service.py)提供 `build`、`review`、`export`、`reconcile_export`、`preview`、`record_sample`、`record_script`、`plan_cleanup`。它从明确 as_of 水位选择资料，核对 policy/purpose、审核及独立 human 决定，记录导出操作并通过 sink 输出文件。

[models.py](../../../src/project_kernel/corpus/models.py)定义 DatasetPolicy、Sample、DatasetManifest、ScriptArtifact 和清理对象；[exporter.py](../../../src/project_kernel/corpus/exporter.py)负责排除/脱敏/输出与 FileSystemSink；[splits.py](../../../src/project_kernel/corpus/splits.py)负责数据切分。输入需要显式 policy、purpose 和 sink 配置，输出是版本化 manifest、排除原因、文件效果和回执，不是直接训练模型。

语料对象与导出 operation 通过项目 Store/UoW 保存；文件写入由 sink 负责。清理只生成计划，不删除文件；导出观察失败保留未知，不因查询重复写入。

## 关系与记录

`depends_on=[K-CONTRACTS, K-STORAGE, K-LEDGER, K-QUERIES, K-IDENTITY]`；`related_to=[K-KNOWLEDGE, K-EVIDENCE, K-BOOTSTRAP, K-RECORDS]`。

| 来源 | 要求及接受范围 |
| --- | --- |
| [P09 交接](../../handoffs/P09.md) | 语料构建、审查、独立导出授权、观察及清理规划的子任务实现资料 |
| [第四轮限制](../../acceptance/G2-round4/limitations.md) | G2-K 单独接受；不能由核心 accepted_g2 推导可生产导出 |
| [REQ-CCR-06/07/11](../../requirements/2026-10-10-continuous-records.md) | 学习文档、画像和干净结构；本轮没有把这些资料注册为样本或启用导出 |

## 限制与变更

此节点没有新的独立签字，当前没有训练/上传任务或后台清理。用户“模型可读的文档”与“语料导出/微调训练”不同，本轮交付前者。用户画像无分数，不自动进入 dataset；若需导出应另外确定范围、授权和接受。

| 日期 | 文档版本 | 变更 | 验证 |
| --- | --- | --- | --- |
| 2026-10-10 | 1.0.0 | 建立可选语料节点，明确开关、授权及文档资料不自动导出 | 静态阅读；无导出操作、测试或 G2-K 接受 |

## 2026-10-12 设计补充

[事实、样本构造与可选 corpus 分工](../../architecture/training-data-boundary.md)对应 [REQ-BOUNDARY-03](../../requirements/2026-10-12-kernel-boundaries.md)。静态复核与限制见[本轮复核](../../reviews/2026-10-12-boundary-review.md)，实际交付和核对见[任务记录](../../records/tasks/2026-10-12-kernel-boundaries.md)。本次只改文档与 skill；评分/总结保留在数据处理，不增加执行依赖或运行接口。

文档版本 1.1.0：补充消费者、外部效果或数据处理职责；无新增行为接受。
