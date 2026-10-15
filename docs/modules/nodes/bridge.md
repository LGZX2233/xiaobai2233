# K-BRIDGE：Node 协议客户端

| 字段 | 值 |
| --- | --- |
| node_id | K-BRIDGE |
| node_kind | module |
| document_version | 1.2.0 |
| updated_at | 2026-10-13（Asia/Shanghai，日期精度） |
| source_version | 1.0.0（项目声明；无独立发布版本） |
| source_revision | `0a619766162682606ad57a9aa4c1926d54c1b891` |
| implementation_status | 已实现纯 Node bridge，无真实平台适配 |
| navigation_parent | K-CORE |
| conversation_refs | [] |

## 职责与源码入口

[client.mjs](../../../bridge/protocol/client.mjs)的 `ProtocolClient` 负责任意字节块分帧、请求 ID/应答匹配、超时、可信 machineContextId 附加和原 key receipt 补查；`inputHash` 与 [canonicalize.mjs](../../../bridge/protocol/canonicalize.mjs)提供协议摘要。输入为宿主提供的 write 回调和收到的字节；输出为写出的 JSON-RPC 和 Promise 结果/错误。

pending 请求、孤立应答和缓冲是客户端内存状态，没有新 SQLite 或 Session 存储。超时不发送取消，不证明成功/失败或重试安全。宿主负责连接、进程启动和身份，不通过 payload 接收伪造 actor/capability。

测试和 test-only vectors 位于 [tests/bridge](../../../tests/bridge/)，与本节点两个运行文件分开。新旧位置见[路径映射](../../development/repository-layout.md)；历史验收仍记录当时路径，迁移没有更新原接受计数。

## 关系与需求

`depends_on=[K-CONTRACTS, K-RPC]` 表示 wire/schema/digest 与对端服务依赖；`related_to=[K-BOOTSTRAP]` 表示外部宿主需适配装配后的真实入口。

| 来源 | 范围 | 状态 |
| --- | --- | --- |
| [AC37/38](../../acceptance/G2-round4/checks.json)、[协议终审](../../reviews/2026-10-09-round4/protocol-peer-review.md) | 指定分帧、乱序、非法输入、timeout 与 receipt 条件 | 原独立接受；原最终 Node 19项是历史计数，本轮未复跑 |
| [REQ-CCR-01/02/03/10](../../requirements/2026-10-10-continuous-records.md) | bridge 可从树进入源码并关联原条件 | 文档已建立，未新增 SDK/宿主兼容性声明 |
| [REQ-SG-01/07](../../requirements/2026-10-10-clean-layout-and-skill-growth.md) | 测试集中、功能目录清洁及历史证据保留 | 已迁移；静态核对见[任务记录](../../records/tasks/2026-10-10-layout-and-skill-growth.md)，未运行测试 |

## 限制与变更

协议客户端本身不实现 DSH Session、Jobs 或工作台。独立的 [AGH 适配器](../../../adapters/agh-plugin/README.md) 使用 stdio machine 通道，提供已有工具和只读多视图，保留完整查询信封与历史水位；知识和评估示例标为设计预览，审批只走独立人工入口。其自测、浏览器检查和隔离安装事实见 [AGH 实施记录](../../records/tasks/2026-10-13-agh-frontend.md)，不新增历史宿主接受。

运行前仍需宿主提供真实 write/read、可信句柄和生命周期处理。AGH 插件关闭其演示进程，不提供自动重连，不改变协议客户端的原验收范围。

| 日期 | 文档版本 | 变更 |
| --- | --- | --- |
| 2026-10-10 | 1.0.0 | 建立客户端入口、摘要、超时及接受记录导航 |
| 2026-10-10 | 1.1.0 | 关联独立测试目录、当前需求及历史路径映射 |
| 2026-10-13 | 1.2.0 | 关联 AGH 只读适配器与独立实施记录；原协议依赖与历史接受不变 |
