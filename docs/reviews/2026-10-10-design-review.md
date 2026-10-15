# 内核设计静态审查

日期：2026-10-10（Asia/Shanghai）。范围是 `kernel_next` 的组合根、执行流、账本与身份、证据与恢复、查询、迁移、knowledge/corpus、Python RPC 和 Node bridge，以及当前维护文档。方法是读取实现、冻结 Schema 与既有证据，追踪入口、授权、持久化和外部效果；不是新一轮独立验收。用户要求停止测试后，本次未继续运行测试或故障探针。

文档版本：1.2.0；当前状态更新于2026-10-10（Asia/Shanghai）。本报告的原发现依据源码基准 `0a619766162682606ad57a9aa4c1926d54c1b891`。RPC 深度、Unicode/id 和响应序列化修复已提交为 `c364539` 并交付 main，仅静态审查、未行为验证；后续同步文档已以 `62bb5d7` 推送。要求见[RPC 修复要求](../requirements/2026-10-10-rpc-resilience.md)，具体核对与 Git 交付事实见[任务记录](../records/tasks/2026-10-10-rpc-resilience.md)和[同步记录](../handoffs/2026-10-10-rpc-fix-main-sync.md)。可选 knowledge 问题仍未修复，也未接入核心 RPC。下文保留原审查阶段的发现和实际动作，不把后续修复回填为历史通过结果。

## 结论

独立核心已经形成从需求与派发到执行、验收、审批、交付和留档的主链路。不可变版本、精确引用、幂等回执、CAS、未知效果和 test/production 区分是设计的主要约束，适合继续作为宿主无关的项目事实核心。

原静态审查发现两处核心 RPC 异常处理缺口，修复已经提交并推送 main；尚无新的行为验证，不能给出“内核没有问题”的结论。知识提升 API 另有授权和效果时序缺口，但没有接入核心 RPC，应在 G2-K 开放前处理。原 G2 的25项87条件独立接受记录保持不变；本次发现及修复不扩大其接受范围，也不授予生产发布许可。

## 设计现状

| 部分 | 已形成的设计 | 需要保留的限制 |
| --- | --- | --- |
| 组合与依赖 | `bootstrap.py` 注入 application、Store、可信上下文与效果 provider；domain 保持纯规则 | 不是完整六边形替换层：application 仍使用 SQL，冻结服务端口与具体类有签名差异 |
| 执行与状态 | task、attempt、approval、delivery 分别持久化；provider 开始前记录 attempt，保留失败及取消待定事实 | executor 调用是同步入口；directory_only 无法阻止进程写到目录外；宿主生命周期属于后续适配 |
| 项目账本 | UnitOfWork 短事务内分配 commit_seq，追加 revision/head_history/audit/receipt，写 head 使用 CAS | 项目库与身份库不共享事务；绑定按持久意图和身份回执恢复，不应宣称跨库原子性 |
| 审批与交付 | 冻结 body digest，当前决定依据单独比较；apply-start 后观察效果，原 key 重放返回原回执 | 关键发布后的 supersession 是另一个事务；直接调用 DesignService 不自带组合根的刷新步骤，apply 仍检查当前依据 |
| 效果与恢复 | DeliveryProvider 分离 apply/observe；归档、备份与恢复由独立 provider 执行；未知效果不能因重放重写 | 没有自动对账 worker；灾难恢复 RPC 仅隔离副本，活动库替换是独立 test 离线维护入口 |
| 证据与来源 | 制品按字节校验，manifest 精确引用；来源身份/序号与本地连续水位持久化 | source_flushed 是本地观察；真实 host final flush 继续 not_configured |
| 查询与历史 | 读事务和 as_of 水位、明确 completeness/gaps、带上下文的分页 token、只读重建 | 无持久 projection checkpoint；读模型及 graph 派生存在扫描成本，token 校验是公开摘要而非授权凭证 |
| 迁移 | 合成只读样本和可信不可变快照，保留来源，幂等导入与孤儿隔离 | 只允许 test，不应推断真实旧项目或生产数据可直接迁移 |
| 可选知识与语料 | knowledge 有上下文预算/反馈/评分 API；corpus 有审核和独立导出授权，默认关闭 | 两者不是用户知识树；knowledge 未接入 RPC，G2-K 未由核心接受自动放行 |
| 平台与交付包 | 自有 JSON-RPC 和 Node bridge 已存在；完整源码树提供冻结 Schema/catalog | 没有真实 DSH/MCP/工作台/Git provider，也没有已接受的 wheel 资源分发路径 |

详细入口与配置以[内核现状](../architecture/current-state.md)为准。

## 核心 RPC 问题

### P1：JSON 解析递归异常可以逃出请求处理

发生阶段：以下为修复前源码基准的静态分析，未运行深度探针。当前已按[REQ-RPC-01](../requirements/2026-10-10-rpc-resilience.md)将 `json.loads` 的 `RecursionError` 转换为 `FrameError`；[修复记录](../records/tasks/2026-10-10-rpc-resilience.md)保留未行为验证状态。

位置：[framing.py 的 parse_json_strict](../../src/project_kernel/interfaces/rpc/framing.py) 与 [protocol.py 的 handle_line/feed](../../src/project_kernel/interfaces/rpc/protocol.py)。`json.loads` 对过深嵌套可能抛出 `RecursionError`，审查时解析器只将 `ValueError` 转成 `FrameError`。`handle_line` 在解码处只捕获 `FrameTooLarge` 和 `FrameError`，通用异常处理在后面的 dispatch 中；因此解码异常不会成为协议错误响应。

触发输入是字节数低于 frame 限制、嵌套深度超出 Python JSON 解码器递归限制的 JSON 对象。深度限制与字节限制是独立条件。`feed` 也不包含这类异常；现有 [stdio test host](../../tests/g2_acceptance/stdio_test_host.py) 直接调用 `server.feed`，该异常路径会结束读取循环并关闭 Store。外部宿主若采用同样的调用方式，一个未认证的输入就可中断连接，而不是只拒绝该请求。

建议在解码处将可预见的解析资源限制异常转换成稳定的协议失败，并明确过深输入的策略。保留同一连接上其他合法请求的处理能力，不依赖宿主 blanket catch 掩盖内核错误。此发现依据静态调用链，未执行深度探针。

### P2：非法请求中的 Unicode 转义可以使错误响应编码失败

发生阶段：以下为修复前源码基准的静态分析，未运行 Unicode 探针。当前已按[REQ-RPC-02/03](../requirements/2026-10-10-rpc-resilience.md)迭代验证所有字符串值与字典键可 UTF-8 编码、只回显匹配冻结 id 正则的 id，并处理响应序列化失败；[修复记录](../records/tasks/2026-10-10-rpc-resilience.md)拥有实现细节与未行为验证状态。

位置：[framing.py 的 parse_json_strict/encode_frame](../../src/project_kernel/interfaces/rpc/framing.py) 与 [protocol.py 的 handle_line/_encode](../../src/project_kernel/interfaces/rpc/protocol.py)。UTF-8 解码检查原始字节，不能拒绝 JSON 字符串中的未配对代理码转义；JSON 解码后，这些值仍可能存在于 Python 字符串中。编码使用 `ensure_ascii=False` 后直接 UTF-8 encode，`_encode` 只捕获 `FrameTooLarge`。

具体路径是 ASCII 字节的 `{"id":"\ud800","method":0}`：method 非字符串时，`handle_line` 在 Schema 校验之前构造 Invalid Request，并原样回显 id；编码这类 id 会抛出 `UnicodeEncodeError`。即使正常 envelope 的 id 规则拒绝该值，提前返回的错误路径也没有经过该规则。它与深度问题一样可能逃出 `feed`。

建议只回显合法 RPC id，并明确处理 JSON 解码后不可编码的字符串和编码失败的兜底响应。不能仅依赖合法请求的 Schema 或原始 UTF-8 检查。此路径未在本次运行探针。

## 可选知识能力的问题

### G2-K 开放前：提升授权与持久意图尚不完整

位置：[KnowledgeService.promote](../../src/project_kernel/knowledge/service.py)。实现检查 `knowledge.share` 和知识 revision 存在，但只把 `human_decision_ref` 纳入摘要与任务字段，没有读取并核验决定的类型、可信来源、action、subject digest、目标范围或有效状态。传入一个引用不等于存在有效的人类授权。

同一方法在 UnitOfWork 记录 promotion_task 之前调用 `shared_sink.write`。崩溃或重复调用时，尚无持久 claim/receipt 阻止再次写入；后续账本 CAS 或幂等冲突也无法撤销已经发生的共享写入。当前 `_guard` 还只检查 project_id，没有检查 store_id。共享提升因此不能沿用核心交付的授权及未知效果保证。

`KernelServices` 没有构造 KnowledgeService，knowledge 命令也未注册，所以这些路径不是本次 G2 核心 RPC 的可达行为。开放 G2-K 时，应先接通可信决定核验、完整 scope 校验和“持久意图 → 一次效果 → 观察/对账”的顺序；当前只宜保留为未接线的可选实现。

## 维护与部署判断

`DeliveryService` 同时承担选择、验收、快照、审批、交付与收尾，`QueryService` 集中多种读模型；SQL、字典字段和接口文档横跨较大模块。后续可按实际职责分离，但应保留同一 UnitOfWork 所需的原子写入，不为追求文件数量把事务切碎。

查询图和来源水位从账本派生，有扫描和排序成本；当前没有持久投影 worker 或生产容量证据。这是部署前的容量评估事项，本次不凭代码体量宣称已经有性能故障，也不要求为 G2 额外增加后台调度。

普通 setuptools 打包只发现 `src` 下的包，而 catalog/Schema/digest 读取仓库外置 `contracts/v1`。现有运行方式依赖完整源码树；发布安装包前需要定义资源携带、路径解析及消费者验证。当前 API 是未发布的内部代码，这不是已经支持的安装路径发生回归。

G3 仍需真实宿主身份、Session/Jobs/工具事件、取消、沙盒、来源 append/flush、连接恢复和人审回调；G4 仍需工作台端到端行为。生产灾难恢复需要真实写者范围、授权、维护停写、回滚和审计制度，不能从 test-store 维护成功推导。

## 原审查阶段的文档处置与证据

本节保存修复前审查阶段的实际动作与结果；当前 RPC 改动、静态核对和 Git 状态另见修复任务记录，不使用本节旧检查代替本轮验证。

README、架构、两份维护计划、ChangeRequest 索引和集成入口更新到第四轮 accepted_g2。旧集成记录与 owner 表明确为历史记录；第三轮/第四轮验收文件、独立签字和冻结输入不重写。新增本报告与现状参考作为维护文档，不回填到旧条件裁决中。

用户停止测试前，实际只读 evidence verifier 返回1281文件、620历史 Python 用例、accepted_g2、problems 为空；实际 Node 宿主复跑为19 passed。沙箱 Node spawn EPERM 与 Python 临时目录 WinError 5 记录留在 `.validation-tmp/pre-main-review/evidence`；Python 没有新的成功复跑，沙箱失败不作为产品反例或通过证据。用户停止测试后，不再运行 Python/Node 测试、复现探针或验收重建。

文档静态核对覆盖9份文件、54个本地链接和单一末尾换行，未发现问题；git diff --check 通过。53项保护输入和217项原验证输入的当前字节摘要与留档一致，运行代码和冻结资料无改动。9份文档保留为本地未提交变更，未创建新分支。

维护文档变化会使历史 manifest 中对应文档摘要与当前树不同；代码和冻结输入仍可按差异独立核对。这个差异应说明，不能用重写历史 hash 消除。本次未修复运行代码，未重新签署 G2，未推送 main；核心 RPC 问题使“无问题直接推主分支”的条件尚未满足。
