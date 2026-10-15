# K-RPC：可信调用与来源入口

| 字段 | 值 |
| --- | --- |
| node_id | K-RPC |
| node_kind | module |
| document_version | 1.2.0 |
| updated_at | 2026-10-10（Asia/Shanghai，日期精度） |
| source_version | 1.0.0 |
| source_revision | `c36453981a2151c7652b54301c0cb5a7a1840856` |
| source_worktree_changes | 源修复已提交并推送 main；后续同步文档不修改 RPC 实现 |
| implementation_status | 已实现；异常处理修复已实施，仅静态审查、未行为验证 |
| navigation_parent | K-CORE |
| conversation_refs | [] |

## 职责与源码入口

| 入口 | 责任 |
| --- | --- |
| [protocol.py](../../../src/project_kernel/interfaces/rpc/protocol.py) `ProtocolServer.feed/handle_line` | initialize、command/query 路由、schema 校验、回执查询与响应 |
| [framing.py](../../../src/project_kernel/interfaces/rpc/framing.py) `LineFramer`、`parse_json_strict`、`encode_frame` | 按换行分帧、UTF-8/JSON解析与输出编码 |
| [invocation.py](../../../src/project_kernel/interfaces/rpc/invocation.py) `InvocationContextRegistry` | 有限寿命项目绑定句柄、可信身份/能力与日志脱敏 |
| [policy.py](../../../src/project_kernel/interfaces/rpc/policy.py)、[session.py](../../../src/project_kernel/interfaces/rpc/session.py) | 支持范围、inflight 限制与 receipt ledger |
| [ingest.py](../../../src/project_kernel/interfaces/rpc/ingest.py)、[source_service.py](../../../src/project_kernel/interfaces/rpc/source_service.py) | 宿主来源映射、可信结果来源和持久 source.ingest |

输入是版本化 JSON-RPC envelope、可信调用句柄和原始来源事件，输出是分帧响应和 ledger 回执。部分协议会话状态只存在进程中；业务回执与来源事实由应用/数据服务持久化，协议本身不宣称跨进程效果成功。

## 关系

`depends_on=[K-CONTRACTS, K-IDENTITY, K-STORAGE, K-LEDGER, K-EXECUTION, K-EVIDENCE]` 涵盖协议验证、身份及 source 服务所消费的数据/用例。`related_to=[K-BOOTSTRAP, K-BRIDGE, K-QUERIES]` 是装配、对端和查询分发关系。

## 需求与验收记录

| 来源 | 精确范围 | 状态 |
| --- | --- | --- |
| [P10](../../handoffs/P10.md)、[AC37/38](../../acceptance/G2-round4/checks.json) | 分帧/乱序/大帧/非法 UTF-8/重复 key/日志通道；timeout 与补查原 key | 历史指定条件 accepted；[协议终审](../../reviews/2026-10-09-round4/protocol-peer-review.md) |
| [AC20](../../acceptance/G2-round4/checks.json) | human 与 machine 可信入口区分 | 历史指定条件接受，不推导新的宿主身份集成已通过 |
| [REQ-CCR-01/02/03/06/10](../../requirements/2026-10-10-continuous-records.md) | 入口、关系、问题学习与上下文 | 文档记录已建立，不新增行为测试 |
| [REQ-RPC-01至05](../../requirements/2026-10-10-rpc-resilience.md) | 深度、Unicode/id、序列化兜底、静态文档与普通主分支同步 | 修复已实施；未行为验证，提交/推送状态由[任务记录](../../records/tasks/2026-10-10-rpc-resilience.md)拥有 |

## 当前问题与版本记录

[2026-10-10 静态审查](../../reviews/2026-10-10-design-review.md)保留基准源码中的递归解析异常与 Unicode 错误响应发现。[当前修复](../../records/tasks/2026-10-10-rpc-resilience.md)已将解码 `RecursionError` 转成 `FrameError`，迭代检查字符串值和字典键可 UTF-8 编码，并只回显匹配冻结 ASCII id 正则的 id，保留原 match 锚点语义。序列化失败转换为 `FrameError`；响应过大保留原错误，其余编码失败返回 `-32603 Internal error` 并保留安全 id，兜底再次失败返回固定 ASCII、null id 响应。修复仅静态审查，未运行测试或复现探针；源码提交与 Git 交付状态由任务记录拥有。自有 stdio 协议不是已认证 MCP；实际 DSH 适配仍属 G3。

| 日期 | 文档版本 | 变更 |
| --- | --- | --- |
| 2026-10-10 | 1.0.0 | 建立协议节点，映射历史条件并保留新静态发现 |
| 2026-10-10 | 1.1.0 | 关联 RPC 修复要求及任务记录，区分已实施与未行为验证 |
| 2026-10-10 | 1.2.0 | 标注已提交源码版本与 main 同步状态 |
