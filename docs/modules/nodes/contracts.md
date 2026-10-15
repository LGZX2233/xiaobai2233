# K-CONTRACTS：冻结协议、类型与摘要

本节点定义独立内核 v1 的公共字段、校验和摘要规则。模块节点与持续记录的元数据是维护文档，不自动加入冻结 RPC payload 或持久化类型。

| 字段 | 值 |
| --- | --- |
| node_id | `K-CONTRACTS` |
| node_kind | `module` |
| document_version | `1.0.0` |
| updated_at | `2026-10-10 Asia/Shanghai` |
| source_version | `1.0.0` |
| source_revision | `0a619766162682606ad57a9aa4c1926d54c1b891` |
| implementation_status | `implemented_frozen_v1` |
| navigation_parent | `K-CORE` |
| conversation_refs | `[]` |

## 责任与源码入口

| 入口 | 责任 |
| --- | --- |
| [contracts/v1说明](../../../contracts/v1/README.md) | v1 Schema、精确引用、两层校验、业务验证与资源定位约定 |
| [command-catalog.json](../../../contracts/v1/command-catalog.json) | 版本化命令/查询声明；不代表provider已配置 |
| [ObjectRef / CommandContext / ResolvedScope / CommandReceipt / QueryEnvelope](../../../src/project_kernel/contracts/dto.py) | Python数据类型、作用域、精确版本和回执 |
| [CommandName / QueryName / ErrorCode等枚举](../../../src/project_kernel/contracts/enums.py) | 冻结命名与状态值 |
| [validate_command_envelope / validate_command_payload等](../../../src/project_kernel/contracts/validation.py) | JSON Schema 2020-12两层验证；`$id`只解析本地资源 |
| [canonicalize / sha256_digest / compute_bundle_digest](../../../src/project_kernel/contracts/digest.py) | RFC8785 JCS规范化、UTF-8字节和SHA-256摘要 |
| [BlockError / KernelError](../../../src/project_kernel/contracts/errors.py) | 公开错误分类、可重试性和安全detail |
| [冻结服务Protocol](../../../src/project_kernel/ports/ports.py) | 冻结服务声明；实际provider消费接口另属internal，不能直接推断签名相同 |

## 字段与版本语义

命令先验证 JSON-RPC envelope，再验证 command/payload；查询同理。Schema 严格拒绝额外字段；权限、actor、同项目FK、状态、证据ready和批准失效仍由服务核验。模型自述的角色或任意引用不能成为可信授权。

ObjectRef 精确到 revision。大整数、序号和金额按协议使用字符串；摘要使用 JCS，不trim或Unicode归一化字符串，不任意排序有序数组。冻结bundle摘要为 `d5fe5816356b0731e78790e997857ea18668cbec16f68673da1f433da07c97cc`；新增维护文档不改变它。

## 节点关系

| 关系 | 目标 | 含义 |
| --- | --- | --- |
| navigation_parent | `K-CORE` | 核心协议职责 |
| depends_on | `[]` | 内核模块依赖本节点；外部jsonschema/jcs依赖由pyproject声明 |
| related_to | [K-DATA](data.md), [K-STORAGE](storage.md), [K-LEDGER](records.md), [K-IDENTITY](identity.md), [K-EVIDENCE](evidence.md), [K-RECOVERY](recovery.md), [K-QUERIES](queries.md), `K-RECORDS` | 多模块消费冻结类型；记录工作流只链接它，不扩展v1字段 |
| conversation_refs | `[]` | 本轮不映射对话 |

## 需求记录

| 来源 | 记录 | 范围与状态 |
| --- | --- | --- |
| 历史冻结 | [v1 Schema说明](../../../contracts/v1/README.md)、[G2 AC12/22/37/38](../../acceptance/G2-round4/checks.json) | 精确版本、稳定快照、分帧/严格JSON和重连回执；接受范围按具体条件 |
| 历史冻结 | [examples与goldens](../../../contracts/v1/examples.json) | 结构与摘要样例；样例本身不证明权限或效果成功 |
| 新增需求 | [REQ-CCR-01/02/03/10/11](../../requirements/2026-10-10-continuous-records.md) | 清晰协议节点、源码/需求/验收元数据、上下文选择和冻结保护 |
| 新增需求 | [REQ-CCR-04/05/06/07/08](../../requirements/2026-10-10-continuous-records.md) | 总结/学习/画像/规则记录采用独立文档工作流；这些需求未纳入v1公共payload |

## 验收记录

| 条件 | 历史状态 | 可定位证据 |
| --- | --- | --- |
| AC12 精确packet与基线 | accepted | [派发证据](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac12_rpc_packet_freezes_b0/execution-evidence.json) |
| AC37 stdio与严格JSON既有条件 | accepted | [真实stdio证据](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac37_real_stdio_compositi0/protocol-evidence.json)、[协议独立审查](../../reviews/2026-10-09-round4/protocol-peer-review.md) |
| AC38 timeout与原key回执 | accepted | [重连证据](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac38_public_receipt_survi0/receipt-reconnect-evidence.json) |
| AC45 冻结输入保护 | accepted | [保护输入](../../acceptance/G2-round4/protected-inputs.json)、[独立终审](../../reviews/2026-10-09-round4/ac45-final-peer-review.md) |
| 本轮维护元数据与新增需求 | `documented_not_newly_accepted` | 不修改v1或签字；未运行测试；[冻结裁决](../../acceptance/G2-round4/checks.json)不扩大 |

## 当前限制与维护

Schema、catalog和digest当前从源码仓库的外置 `contracts/v1` 读取；普通wheel独立资源路径未接受。冻结服务Protocol与具体服务不全同签名，调用方需核对实际入口。[设计审查](../../reviews/2026-10-10-design-review.md)还记录 JSON深度解析异常和错误响应Unicode编码缺口；本轮文档没有修复它们，历史AC37不等于这些新增路径已经接受。

新增能力若需要RPC或持久化字段，先建立明确版本与变更记录，再更新消费者与接受依据。本轮持续记录、描述式用户画像和可插拔规则使用文档与既有规则机制，不手改冻结Schema、examples、goldens或bundle manifest。

## 版本与变更记录

| 日期 | 文档版本 | 记录 | 验收影响 |
| --- | --- | --- | --- |
| `2026-10-10 Asia/Shanghai` | `1.0.0` | 建立冻结协议节点，列明资源/签名及RPC静态缺口 | 仅文档；v1冻结字节与独立签字保持不变 |
