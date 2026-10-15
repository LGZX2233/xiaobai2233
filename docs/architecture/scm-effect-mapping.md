# 公司代码管理与交付效果映射

文档版本：1.0.0；更新日期：2026-10-12（Asia/Shanghai）。源码依据：`16410c9fbf4a8507445b4603e371e701614e4499`。归属 [K-DELIVERY](../modules/nodes/delivery.md)，对应 [REQ-BOUNDARY-02](../requirements/2026-10-12-kernel-boundaries.md)。状态：SCM 接入设计要求，未实现 Git 交付，未做真实宿主验证。

## 当前交付范围

[DeliveryService.delivery_request](../../src/project_kernel/application/delivery/service.py) 当前要求目标 `method="bundle"`，并构造 bundle 交付。[DeliveryProvider](../../src/project_kernel/internal/delivery_provider_ports.py) 是显式注入的效果接口；现有 [BundleDeliveryProvider](../../src/project_kernel/evidence/delivery_provider.py) 输出文件包。仅实现另一个 provider 不能让冻结 v1 自动支持 Git push 或 merge。

SCM 集成方负责定义代码管理侧目标、执行和只读观察；内核负责持久操作身份、批准依据、claim/apply-start/epoch 和状态结算。新的 push/merge 目标、批准范围与证据字段需要独立设计及兼容性决定，不修改冻结 `contracts/v1` 来宣称已有支持。仓库日常提交或推送也不自动构成内核交付事实。

## 先定义批准的效果

| 目标 | 可观察结果 | 不能据此推出 |
| --- | --- | --- |
| 创建本地 commit | 指定仓库内存在精确 commit/tree | remote 已接受或分支已经更新 |
| 推送 remote ref | 指定 remote 的目标 ref 满足约定，并能关联操作和内容 | 已合并目标分支或已经部署 |
| 合并目标分支 | 受批准目标及合并策略约束的结果 commit/tree 已成立 | 生产运行成功 |

执行前固定仓库身份、remote、ref、期望前置对象、操作类型和完成判据。审批方批准的目标与 provider 实际写入目标必须一致。分支可能随后前移或被强推，因此需声明判据是某时刻的 ref 状态、历史接受记录还是持续条件；观察证据保留观察时间和对象身份，不能只记录易变的分支名。

## 字节证据与 SCM 对象如何关联

内核 manifest digest、候选内容摘要、Git blob/tree/commit 对象 ID 各有不同输入和算法，不得直接相等比较。SCM 适配层需形成可复核关联：持久 operation_id → 获批目标与前置条件 → 精确 SCM 对象 → 固定清单中的路径和字节 → 对应 manifest digest。

映射至少说明路径规范化、文件 mode/可执行位、符号链接、LFS 指针与实际内容、submodule 对象、换行/filter 转换，以及额外、缺失或排除文件的处理。Git tree 包含路径和 mode，commit 还包含父提交及元数据；同样的工作区字节不意味着同一个 commit，工作区内容也不能单独证明 remote 接受。映射版本、对象与字节证据由适配方留存；证据不足时保持 unknown。

当前应用传给 `_normalise_effect` 的 expected_digest 是 [ArchiveManifest.digest()](../../src/project_kernel/evidence/archive.py)；`applied` 回执的 `verified_digest` 必须匹配这个摘要。该字段不是任意 Git hash，也不是 delivery snapshot digest。未来 SCM 映射必须证明其所指的 manifest 与实际效果一致，不能把摘要复制到回执就当作验证。

## 回执与观察语义

| 字段或结果 | 当前内核要求 | SCM 接入需额外建立的依据 |
| --- | --- | --- |
| operation_id | 回执匹配持久操作身份 | SCM 请求或记录可关联同一操作；同内容的他人提交不足以冒充此操作 |
| applied + verified_digest | 匹配固定 manifest 摘要；不普遍要求 execution_terminal=true | 获批 SCM 效果已达成且对象/字节映射已核验 |
| absent_final | execution_terminal=true 或经内核校验的 fence_evidence_ref | 足以证明该操作不会再产生所批准的效果；暂时缺少 ref/文件不足以证明 |
| absent_pending / unknown | 保持未确定状态及阻断 | 超时、查询失败、无法关联操作或映射不完整均不得猜为成功或无效果 |
| observe | 只读，不能修复、推送、合并或重放写入 | 可读取 SCM 状态及操作证据；网络恢复不授权再次写入 |

claim 的 lease_until 与 epoch 是内核实际状态约束，不等于跨 SCM 系统的 fencing。未来适配方需要另行说明外部幂等、持有者排他性及 fencing 保证；不能把 operation_id 的去重作用称为完整外部租约。

超时后由宿主调度显式观察或人工升级。unknown 随时间老化可以触发提醒，却不能仅凭 TTL 变成 applied/absent_final。评分或失败总结接口只记录原因和待确认项，不触发执行重试。

## 接入前的接受要求

独立场景应覆盖：本地 commit 成功但 push 失败；push 超时后 remote 实际接受；remote ref 前移或被强推；同内容不同 commit；filter/LFS/submodule 映射；前置条件冲突；旧 epoch 回执；缺失目标但外部操作仍在运行。先确定新目标契约和证据所有者，再用真实宿主验证。本文只补充设计说明，当前 `release_approved=false` 不变。
