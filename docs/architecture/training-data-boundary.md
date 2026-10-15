# 事实留存与训练样本的职责

文档版本：1.0.0；更新日期：2026-10-12（Asia/Shanghai）。源码依据：`16410c9fbf4a8507445b4603e371e701614e4499`。归属 [K-CORPUS](../modules/nodes/corpus.md)，对应 [REQ-BOUNDARY-03](../requirements/2026-10-12-kernel-boundaries.md)。状态为现有可选实现的职责说明，无新增样本、导出或训练接受。

## 事实与样本分开管理

不可变 revision 记录需求、尝试、拒绝、未知、验收、审批和交付过程。它们支持留档、检索与上下文组装；成为训练样本还需要明确抽取单元、输入输出范围、标注依据及数据用途。拒绝命令不必然是负样本，失败不必然说明方法错误，applied 不必然代表输出质量良好。未知保持未知，后续纠正通过新事实和样本版本表达，不覆盖原过程。

| 责任方 | 输入 | 输出与责任 |
| --- | --- | --- |
| 核心留存与查询 | 业务命令、可信来源及外部效果 | 精确 revision、来源引用、提交水位、缺口和证据 |
| 上游样本构造器 | 固定事实范围与明确构造规则 | candidate Sample；确定任务单元、输入/输出、标签依据、排除原因和构造版本 |
| 可选 corpus | candidate Sample、policy、purpose 和切分规格 | 样本记录、审核、dataset manifest、独立导出授权及效果观察 |
| 训练消费者 | 获准导出的固定 dataset | 训练与评测配置、运行结果；不改变核心通过/批准状态 |

样本构造可由下游流程或专用适配器完成，不要求全部在 corpus 之外重做。当前没有从任意 revision 自动推导 instruction-response、奖励或正确标签的通用转换器；该能力需要具体任务及另行接受。核心无需为训练目标改变冻结 revision schema。

## 已有 corpus 能力

[Sample](../../src/project_kernel/corpus/models.py) 已有 input/output、source_refs/source_digests、artifact 引用、verification_labels、failure_type、quality_flags、group_id 和 metadata。[CorpusService.record_sample](../../src/project_kernel/corpus/service.py) 接受可信内部写者构造的样本并写入 sample revision；build 在明确 as_of 下读取已有样本。不能据此宣称公开 RPC 已提供通用样本构造入口。

Sample 是候选，不能自行声称已审核。[SampleReview](../../src/project_kernel/corpus/models.py) 与独立导出授权分别管理；policy/purpose、脱敏和来源条件约束可导出范围。保持事实账本与解释标签分离：verification 标签引用具体候选和检查版本，人工标签注明来源；标签变化创建可追踪的更新，不把训练标签写回核心验收结果。

[splits.py](../../src/project_kernel/corpus/splits.py) 按 project + task lineage 和固定 seed 确定 train/eval/test。相同任务的尝试、修复或相关会话样本应进入同一组；构造器负责正确传入关联身份，不能用新 sample_id 把同一任务拆到多个 split。该机制防止已知同任务泄漏，不自动识别跨任务的复制内容或语义近重复，后者由数据集构建规则另行处理。

## 可再现与失败样本

每版数据集应能定位事实水位、精确来源与字节摘要、构造器/模板/标注规则版本、policy、脱敏版本、split seed、样本审核和导出授权。固定样本来源不代表标签永远正确；纠正或撤回来源时，另记受影响样本和下游处理决定，不改写冻结历史证据。旧 manifest 不能被用来声称后来撤回的数据仍适合继续消费。

纳入失败样本前区分：方法缺陷、适用范围不匹配、旧前提、调用误用，以及环境/provider 故障或尚不明确的外部效果。保留预期/实际、错误证据、影响和未决项；未知根因不能变成确定负标签。skill 四维评估只描述特定方法版本的一次观察，不能直接转换为训练奖励或用户分数，详见[评分与失败处理范围](skill-growth.md#数据处理接口与评分范围)。

用户学习画像不自动进入 dataset；导出需要明确数据范围与授权。本文不授予训练、上传或外部写入权限，也不把修改文档当成样本构造行为已经验证。

## 当前启用状态

`enable_corpus=False` 是默认值，G2-K 尚未单独接受。knowledge 未装配到核心 RPC，与 corpus 共用留存不意味着两者已形成自动运行链路。当前可以提供事实消费与样本处理的设计入口，不能声称默认产出训练集或可生产导出。

后续接受需覆盖样本来源缺失/摘要不符、未审核与未授权导出、未知标签保留、同任务修复不跨 split、撤回来源的影响处理，以及真实 sink 效果观察。本文未执行这些行为场景；核心历史合成验收不替代训练数据质量或真实宿主接受。
