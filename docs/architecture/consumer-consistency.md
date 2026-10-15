# 消费者一致性与上下文再现

文档版本：1.0.0；更新日期：2026-10-12（Asia/Shanghai）。源码依据：`16410c9fbf4a8507445b4603e371e701614e4499`。本文由 [K-QUERIES](../modules/nodes/queries.md) 与 [K-KNOWLEDGE](../modules/nodes/knowledge.md) 索引，对应 [REQ-BOUNDARY-01](../requirements/2026-10-12-kernel-boundaries.md)。状态为设计说明及静态核对，尚无新增宿主行为接受。

## 同一事实来源，不同消费水位

内核作为上下文工厂与执行编排的事实基础，保留不可变 revision、精确引用、指针历史和提交水位。模型、前端、训练数据处理各自选择消费水位；它们不必同时刷新，但必须能说明所读项目、Store、版本和缺口。执行 provider 的现场状态只有经结算成为已提交记录后，才属于该水位下的内核事实。

| 消费者 | 读取约定 | 更新时机 | 必须保留的信息 |
| --- | --- | --- | --- |
| 前端权威视图 | 查询开始时确定的已提交 `as_of_seq`，按该水位解析 head_history | 每次刷新可采用更高水位；同一分页过程固定水位 | 查询水位、来源水位、freshness、completeness、gaps |
| 模型上下文 | 固定水位下选择精确 revision 和材料字节，再固定组装输入 | 显式构建下一份上下文，旧输入不被最新 head 替换 | 精确来源、内容摘要、组装规则与实际请求内容 |
| 训练处理 | 固定事实范围，经样本构造、审核和导出形成独立版本 | 构建下一版 dataset | 样本来源、构造与标注版本、审核及导出依据 |

前端可以展示本地编辑、请求进度或 provider 暂态，但需与已提交事实分别标识；“近实时”不授权读取尚未提交的 revision 作为权威结论。例如模型输入固定在水位 100，而前端刷新到 105，两者展示不同版本符合约定。若要求比较相同版本，应让双方读取 100，而不是改写旧上下文。

`commit_seq` 表示事实进入账本的提交顺序，不是 provider 事件实际发生时间。迟到回执在后续提交中追加；旧水位表示当时已经留存的知识，不因后来获知事实而回填。按业务发生时间重建事件序列属于另一个投影，消费者需明确时间来源与缺失情况，不能把外部时间戳直接当作提交水位。

## 模型输入再现需要保留什么

仅保留一个 snapshot digest 不足以重建模型请求。下表是宿主上下文组装器的设计要求，不表示当前核心已保存完整模型请求。

| 材料 | 保留要求 |
| --- | --- |
| 事实范围 | project_id、store_id、as_of_seq、精确 ObjectRef 和来源缺口 |
| 实际内容 | revision payload、外部材料与制品的可读取字节及摘要；摘要不能替代丢失的内容 |
| 组装规则 | 组装器与模板版本、配置、稳定排序、预算、裁剪及排除原因 |
| 计量 | tokenizer 或估算器版本、预算单位；估算必须标明估算 |
| 请求 | 实际 system/messages/tool definitions 等输入与其摘要、所用模型标识和参数；敏感资料的访问与保留规则由宿主另行确定 |

同一 revision 序列只有在材料内容、组装版本和配置固定时，才能要求生成同一输入字节。模型输出还受模型服务及其运行条件影响；输入可再现不等于输出必然相同。材料丢失、摘要不符或版本未知时报告不可再现，不能用当前 head 或猜测内容补齐。

[ContextResolver](../../src/project_kernel/knowledge/resolver.py) 已实现 mandatory 材料缺失、过期或超预算时阻断，optional 排序并记录 exclusions。[KnowledgeService.verify_manifest](../../src/project_kernel/knowledge/service.py) 核对来源存在及有值的 content_digest；它不证明所有外部内容与最终请求已经完整留存。交付中的 `context_manifest` 和 `delivery_snapshot` 固定交付依据，不等于完整模型请求。

## 当前实现与后续接受

[QueryService](../../src/project_kernel/data/queries/service.py) 使用短读事务与历史指针；[分页和水位](../../src/project_kernel/data/queries/watermarks.py) 绑定查询、项目、Store、过滤条件及 as_of。该机制为消费者提供固定读取范围，不强制多个消费者同步。

当前静态核对发现 `_describe_attempt` 的 verification_index 分支按 `report_ref` 字典序取报告，且未约束 as_of；因此不能把固定水位设计扩大解释为所有查询分支均已正确实现。具体风险与验证空白见[复核记录](../reviews/2026-10-12-boundary-review.md)。修复与历史查询行为验证另行处理。

真实宿主接受需要覆盖：前端更新后旧模型输入仍按原版本再现；同水位跨页不混入新提交；缺失或改变的材料明确失败；mandatory 不被静默裁剪；迟到事实不污染旧水位。本文没有运行这些场景。knowledge 仍未接核心 RPC，完整请求留存与组装器版本管理属于待设计、待接入部分。
