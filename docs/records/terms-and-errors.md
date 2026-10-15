---
record_id: CCR-TERMS
record_version: 2
updated_at: 2026-10-10
timezone: Asia/Shanghai
source_revision: 0a619766162682606ad57a9aa4c1926d54c1b891
source_worktree: RPC resilience fixes and documentation after source_revision; actual commit owned by RPC task record
status: active
requirement_ids: [REQ-CCR-06, REQ-CCR-10, REQ-RPC-01, REQ-RPC-02, REQ-RPC-03, REQ-RPC-04]
module_ids: [K-RECORDS, K-RPC]
acceptance_status: not_behaviorally_validated
---

# 项目术语与错误资料

本页解释当前项目中的术语和已定位问题，供任务学习与维护上下文读取。RPC 修复已在当前工作树实施，仅静态审查、未行为验证。错误条目保留静态发现的条件；原分析由[设计审查](../reviews/2026-10-10-design-review.md)拥有，当前修复状态由[RPC 修复记录](tasks/2026-10-10-rpc-resilience.md)拥有。

## 项目术语

| 术语 | 当前项目含义 | 使用时要保留的区别 |
| --- | --- | --- |
| 模块节点 | 文档中稳定命名的一项职责，指向源码、需求、验收和变更记录 | 不等于单个文件；一个文件可以服务多个节点 |
| 模块树与关系图 | 树给出主要导航父子关系；图记录依赖、需求、证据等额外关联 | 多对多关系不能只靠文件夹位置表达；见[学习资料](learning/2026-10-10-modules-and-rules.md) |
| accepted_g2 | 独立核心冻结 G2 条件获得历史接受 | 不表示 `release_approved=true`，不覆盖新增功能或生产部署 |
| command receipt 的 accepted | 持久命令被接受及其回执可追溯 | 不等于 provider 外部效果已经成功 |
| unknown | 现有证据不能确认效果或结果 | 不能当作成功、失败或零费用，也不能因此自动重写效果 |
| 精确来源版本 | 结论所依赖的 Git 提交、业务 revision 或证据版本 | 文档更新时间不是源代码版本；不同来源须分别注明 |
| claim / apply-start / observe | 外部效果前的持久意图、效果开始记录及随后观察 | 把写入放到持久 claim 前会破坏重复调用及崩溃恢复判断 |
| 可插拔规则 | 项目配置的额外限制与解释 | 不能撤销核心项目隔离、审批和证据真实性要求 |
| skill | 可复用的工作方法和维护步骤 | 不是项目事实本身，不自动授予运行或测试权限 |

## 静态问题索引

| ID | 触发条件与影响 | 当前依据和状态 | 后续维护所需记录 |
| --- | --- | --- | --- |
| ERR-RPC-DEPTH | 修复前基准中，JSON 字节数低于 frame 限制但嵌套过深时，`RecursionError` 没有转换为协议失败，可能逃出读取循环 | [原发现](../reviews/2026-10-10-design-review.md#核心-rpc-问题)；当前已转换为 `FrameError`，见[REQ-RPC-01](../requirements/2026-10-10-rpc-resilience.md)；仅静态审查、未行为验证 | 实际源码提交见修复任务；后续如获授权，另记连接处理结果与验证证据 |
| ERR-RPC-UNICODE | 修复前基准中，非法请求含未配对代理码 id 时，提前返回的错误响应回显它，UTF-8 编码可能失败并逃出 `feed` | 当前迭代检查全部字符串和字典键，只回显匹配冻结 id 正则的 id；编码失败有 `-32603` 兜底，见[REQ-RPC-02/03](../requirements/2026-10-10-rpc-resilience.md)及[修复记录](tasks/2026-10-10-rpc-resilience.md)；仅静态审查、未行为验证 | 保留冻结正则 match 锚点语义；后续验证和源码提交另记 |
| ERR-KNOWLEDGE-PROMOTE | 引用人类决定但未读取核验决定；共享 sink 写入发生在持久 promotion 记录之前；scope 校验缺 store_id | [知识提升问题](../reviews/2026-10-10-design-review.md#可选知识能力的问题)；可选库 API 静态发现，未接入核心 RPC、未修复 | 可信决定和 subject/target 核验、完整 scope、持久意图与效果观察、开放前独立验证 |

原发现引用源码基准为顶部 `source_revision`；当前修复依据包含 `source_worktree` 中基准后的两个 RPC 文件，不是该基准已有行为。没有相关 attempt、实际失败输出或运行验证证据时，不生成虚构引用。实际源码提交、Git 交付与验证状态由修复主记录拥有，旧发现的来源版本继续保留。

## 解释要点

字节限制控制请求体大小，递归限制控制嵌套处理深度，两者保护的资源不同。原始请求可正确 UTF-8 解码，并不说明 JSON 转义展开后的每个字符串都能再次 UTF-8 编码；错误响应也必须能安全处理无效输入。

授权引用和实际授权是不同事实。引用需要指向可信、有效且与当前 subject 和目标匹配的决定；外部写入发生后才记录意图，无法用后来的事务回滚撤销先前效果。理解这些区别有助于阅读核心交付设计，但不能据此声称可选 knowledge 已满足相同保证。

## 修订记录

| 记录版本 | 更新时间 | 内容 |
| --- | --- | --- |
| 1 | 2026-10-10 | 建立项目术语和三项静态问题的学习索引；未新增运行结果或接受结论 |
| 2 | 2026-10-10 | 更新 RPC 修复及未验证状态，保留原发现阶段和未修复 knowledge 问题 |
