---
record_id: BOUNDARY-TASK-20261012
record_version: 5
updated_at: 2026-10-13
timezone: Asia/Shanghai
source_revision: 16410c9fbf4a8507445b4603e371e701614e4499
source_worktree: uncommitted architecture, skill and record documents; 同轮路线 A 决策与执行流校准，runtime 未改
status: documented
requirement_ids: [REQ-BOUNDARY-01, REQ-BOUNDARY-02, REQ-BOUNDARY-03, REQ-BOUNDARY-04, REQ-BOUNDARY-05, REQ-BOUNDARY-06, REQ-BOUNDARY-07, REQ-BOUNDARY-08, REQ-BOUNDARY-09, REQ-BOUNDARY-10, REQ-BOUNDARY-11, REQ-BOUNDARY-12, REQ-BOUNDARY-13]
module_ids: [K-DATA, K-QUERIES, K-KNOWLEDGE, K-DELIVERY, K-CORPUS, K-RECORDS, K-EXECUTION, K-STORAGE, K-DESIGN]
acceptance_status: not_behaviorally_validated
---

# 架构边界与 skill 范围补充

本轮按用户要求核对“上下文工厂 + 执行编排”定位及旧评价，补充消费者、SCM 和训练职责，并明确 skill 评分及失败总结只属于数据处理。需求主记录是[本轮要求](../../requirements/2026-10-12-kernel-boundaries.md)；前段采用 kernel-maintain-records、kernel-grow-skills 和外部 skill-creator 的相关指导，未创建子代理。用户随后要求实施多分发代理，本轮路线 A 校准按此要求拆分，记录如下。

## 交付与判断

| 交付 | 内容及限度 |
| --- | --- |
| [消费者一致性](../../architecture/consumer-consistency.md) | 前端权威事实已提交；模型固定完整组装输入；不同水位和迟到事实的含义 |
| [SCM 效果映射](../../architecture/scm-effect-mapping.md) | 当前 bundle 限制；未来 SCM 的批准目标、对象/字节映射和效果观察要求 |
| [训练职责](../../architecture/training-data-boundary.md) | 核心事实、候选样本构造、可选 corpus 审核/切分/导出、训练消费分工 |
| [评价复核](../../reviews/2026-10-12-boundary-review.md) | 核心方向成立；纠正未提交事实、无样本入口、无 decision/lease、异常提交及全部索引未读等过强判断 |
| [技能成长](../../architecture/skill-growth.md)与[模板](../skills/assessment-template.md) | 单版本/单次观察的四维评分与充分失败分析；不回流执行、授权或训练奖励 |
| [skill 1.1.0 修订](../skills/2026-10-12-grow-skills-revision.md) | 新版本 trial/not_validated，旧版历史保留，不伪造成功观察或评分 |

六个既有节点及文档入口、skill registry 与模块 registry 同步维护，仍为 23 节点；没有修改导航关系、运行依赖或 frozen v1。没有新增 Python/wire 接口、provider、worker 或 runtime skill loading。发布、knowledge、corpus 和 RPC 验证限制保持不变。

## 实际阅读范围

复核主要覆盖查询水位/报告分支、交付 provider 与效果归一化、delivery_request/decision/terminate/UoW、blocker 同事务写入、knowledge resolver/scoring/score/promote、corpus Sample/record_sample/build/splits、打包配置和 digest，以及其 owning nodes/current-state/skill 文档。精确源码以顶部提交为基准；本轮未改源码。

此前及本轮部分大文件输出有截断，关键结论所需片段已小范围核对。尚未完成全部约 90 个 Python/JS 文件的逐行阅读，不将本记录称为全面源码审查。未重新运行旧评价中的 620/19 项测试、构建 wheel、接入真实宿主或运行 RPC 故障场景。全量静态审查和行为验证深度各自独立，不能互相代替。

## 本次工具失败分析

| 失败 | 阶段、证据及已确认原因 | 影响、修正与复核 |
| --- | --- | --- |
| Get-Content 找不到路径 | 文档读取阶段；报错对象是根目录 skill-growth.md 和不存在的 2026-10-10-skill-growth.md。把交接摘要简称误当实际路径，未先核对目录。 | 没有文件写入；改读 docs/architecture/skill-growth.md 与实际 clean-layout-and-skill-growth 需求。相关正文随后读取成功；这不是内核调用失败。 |
| apply_patch 上下文匹配失败 | 文档修改阶段；试图匹配独立的结尾句，但真实句子位于长段落中。工具报告 Failed to find expected lines。 | 同一 exec 中前一补丁已更新页头，失败的第二补丁没有应用；移除无必要结尾匹配，按现存标题插入，重试成功。后续核对发现并移除重复 Review And Revise 标题。 |
| 大批读取输出截断 | 证据读取阶段；tool output 明确 Warning: truncated output。合批后超过输出预算，不能假定已读完整内容。 | 改用关键符号定位和小段读取；未见部分仍列阅读缺口，不据截断内容得出全量审查完成。 |
| PowerShell 解析文件参数失败 | 路线 A 文档定位阶段；命令使用 Bash 风格的 `nodes/{delivery,storage,...}.md`，PowerShell 返回 ParserError / Missing argument in parameter list，rg 尚未执行。已确认是调用命令语法，不是文件缺失或内核错误。 | 无写入或外部效果；改为逐个明确文件参数后同项 rg 查询成功。失败不影响代理的已完成读取；不据此降低 skill 分数。 |
| 预设目录与源码路径不存在 | 路线 A 静态定位阶段；主代理把不存在的 `scripts/` 加入搜索，rg 报 os error 2；代理回报误查 `verification/service.py`、`rpc/handlers.py`、`rpc/server.py`、`application/common.py`、`application/validation.py`。已确认是依据命名猜布局而未先做文件发现，不是接口在运行中消失。 | 没有写入或外部效果；主代理放弃不存在的脚本目录，采用只读静态核对；代理用 `rg --files` 与函数名检索定位 `bootstrap.py`、`application/delivery/service.py`、`application/design/references.py` 和 `data/queries/service.py` 并完成相关读取。该错误不构成内核调用或 skill 方法失败证据。 |
| 同文件 Delete/Add 补丁被拒 | 路线 A 身份页代理回报：单个 patch 同时 Delete/Add 同一目标被工具拒绝，未落盘。已确认是补丁操作格式，不是文件内容冲突或运行异常。 | 改为单次明确路径 UTF-8 写入三个独占文件，并检查链接、版本、尾换行和差异；没有影响其他代理文件或 runtime。 |
| rg 路径通配符未展开 | 最终只读复核阶段；源码复核代理回报以 `executor*` 作为路径参数导致 os error 123。已确认是路径通配符未被展开，不是源码接口故障。 | 没有写入或外部效果；改用明确的 `internal` 目录后检索成功，完成六页及需求/任务的复核。该错误不构成运行验收或 skill 方法失败证据。 |
| 节点静态校验器误报 | 最终核对阶段；自编只读检查返回节点关系/父节点不一致。原因是把后面的关系表字段覆盖到页首元数据，且仅识别关系表，漏读部分节点的内联关系列表；首次修正后仍漏读等号两侧有空格的列表。两次报错都是检查器解析限制，不是已确认的文档关系缺陷。 | 没有修改被检查的节点或 registry；将元数据读取限定在首个章节之前，同时解析关系表和内联列表，并允许等号两侧空白后复验。链接计数按本次 17 文件的 Markdown 本地链接目标统计，不沿用先前脚本的 311 计数。 |

这些是本轮文档工具操作的失败，不是运行内核、provider 或 skill 方法失败的行为证据；不据此为用户或旧 skill 打分。错误原因可由路径/补丁上下文与工具消息确认，没有发现外部效果或未知执行重试。

## 静态核对与后续

实际运行了 `quick_validate.py .agents/skills/kernel-grow-skills`，结果为 Skill is valid；它只检查 frontmatter/命名等静态规则。`git diff --check` 退出 0；Git 的 LF→CRLF 提示是工作树换行配置提醒，不是验证失败。

自编只读 Python 静态核对检查了 JSON 解析、Markdown 本地链接及标题锚点、23 节点路径/关系/无环导航、skill 当前版本与历史条目、尾换行和文件修改范围：首轮 23 个文件、322 个本地链接，errors=[]；加入维护观察记录后的最终增量核对为 24 个文件、324 个本地链接，errors=[]。模块关系与节点数不变；冻结、runtime、测试、签字和原始证据均未修改。检查结果只对文档完整性有效。

记录维护 skill 的本次范围观察见[评估记录](../skills/2026-10-12-maintain-records-use.md)，新版成长 skill 不登记成功调用。报告排序/历史污染、索引写入覆盖、knowledge 提升和完整模型输入保留等风险由[复核记录](../../reviews/2026-10-12-boundary-review.md)拥有。本轮未修运行问题，SCM 仍是未来接入要求，skill 新版仍待真实适用场景观察。没有提交、推送或发布。

## 追加轮交付（同日追加）

用户在同一会话继续补全执行流并对存储分层给出决定，要求把新需求**追加进本轮记录**且**不简略描述**。因此本轮版本推进为 2，新增 REQ-BOUNDARY-06~11（执行流映射、双层存储与收敛公理、并行分支与方案包、模型收尾身份、耦合度量与裁决边界、智能体交换与表单实时）及常设工作要求 REQ-BOUNDARY-12（设计需主动讨论技术方案与细节）。

| 交付 | 内容及限度 |
| --- | --- |
| [执行流映射](../../architecture/execution-flow-mapping.md) | 八阶段逐段映射；既有独立目录多尝试基础与待新增显式分支/方案包/收敛模型分别说明 |
| [双层存储与收敛公理](../../architecture/dual-layer-storage.md) | 项目/模块各有架构与需求；过程留存和正式纳入分开，三条件只约束后者 |
| [并行分支与方案包](../../architecture/parallel-branches.md) | fan-out/branch/converge 候选结构与命令；未采用方案也可留存；分支目录分离，正式采用与现有交付的映射待设计 |
| [模型收尾身份](../../architecture/model-review-identity.md) | 已选 A（模型评分、人类确认入库）；B 保留为未采用备选；意见、验收、人审授权分别建模 |
| [耦合度量与裁决边界](../../architecture/coupling-metric-boundary.md) | 依赖与职责分布等可复现度量进内核数据处理；高聚合判据另定；杂乱与解耦建议由收尾模型提出 |
| [智能体交换与表单实时](../../architecture/agent-exchange-and-live-forms.md) | 实时归编排层；可溯源模型交换 model_exchange 归内核 |

本轮**未改源码**，仍为 23 节点；未新增 wire/Python API、provider、worker、schema 或后台服务；未修改冻结 `contracts/v1`、历史签字与原始证据。需求主记录版本 3 反映已选 A 及措辞纠正，运行接受状态与 `release_approved=false` 保持不变。设计讨论依 REQ-BOUNDARY-12 给出候选方案、取舍理由与影响面；实施按用户要求拆分代理任务。

### 追加轮的判断与待拍板项

讨论中给出三项不同意见（不默认放开人类闸门、显式分支不能只靠查询拼、实时通道由编排层负责）。需求编号已确定续用；用户明确“走a”，身份路线 A 已选。多层分支嵌套仍未决定，不能由路线选择推断。候选接口的 schema、幂等和并发处理仍待设计；没有因此启动运行实施。

### 追加轮的阅读范围与未验证项

本轮追加的映射与判断基于对 `domain/flow.py`、`domain/delivery/*`、`application/{attempt,delivery}/service.py`、`evidence/{delivery_provider,archive}.py`、`data/queries/service.py`、`corpus/splits.py`、`docs/modules/nodes/*` 的定向阅读，以及既有的 `consumer-consistency.md`、`scm-effect-mapping.md`、`training-data-boundary.md` 三轮设计文档。未重新运行测试，未接入真实宿主，未行为验证并行分支、收敛命令、model_exchange 或耦合度量；上述均为设计说明，不构成新增行为接受。

## 2026-10-13 会话总结与未决项归档

同日会话（延续 2026-10-12 边界讨论）用户再次确认整体思路并要求总结记录：

- 执行流确认形态：设计模型读整体架构、问询理解需求、拆分需求并给出执行范围与验收标准 → 分发并行执行对话 → 执行在沙盒处理，可提交多实现方案包并按不同实现评分 → 任务表单通讯验收 → 收尾模型评分审阅、处理模块杂乱与低耦合高聚合 → 并入主库；未采用方案包也有保存入库的可能。
- 存储确认形态：项目整体（L0）与模块独立（L1）两套架构和需求，L1 主要供执行流阅读；模型更多是读库，表单实时更新与模型间交互提问。
- 设计方法要求：设计部分更主动讨论技术方案与细节（已有固定要求 REQ-BOUNDARY-12）。

本轮确认未新增事实，均为上述既有文档要求的确认；R1 规格与既有架构页已覆盖。用户再次确认仍待拍板或待设计的未决项（均不实施）：L1 物理形态（同库逻辑分区或独立库）、多层分支嵌套是否支持、收敛命令名/schema/幂等语义、耦合度量首版范围与高聚合判据、`model_exchange` schema 与权限、表单字段 diff 投影、未知（unknown）老化提醒策略与执行层收敛 SLA。本轮不改源码，不启动运行验收，`release_approved=false` 保持不变；未决项的后续设计记录按[持续记录架构](../../architecture/continuous-records.md)在到达相应实施阶段时再开新任务记录，不在本记录中预写结论。

最终只读检查：本段仅编辑任务记录与项目总结，无源码/运行时/冻结文件改动；链接均指向既有文档。

## 路线 A 确认与执行流校准（本轮版本 3）

2026-10-12 当前会话用户明确“走a”，并重述执行流及项目/模块两级架构需求，随后要求“实施时多分发代理执行”。本次使用 kernel-maintain-records 2.0.0，范围是设计事实与记录维护。三名代理分别编辑身份/映射/度量三页、存储/方案包/交换三页，以及独立只读核对源码；主代理同步本轮需求、节点及摘要并核对合并结果。修改任务按文件分开，复核不授予代理额外运行或外部操作权限。

### 判断、取舍与影响

整体分工可成立：设计模型确定模块需求、范围与验收标准；执行模型在隔离目录中探索并封包；收尾模型依据测试和度量比较方案、提出整理建议；人类确认最终纳入。编排层负责调度、实时交互及执行已授权动作，内核保存精确事实与引用。路线 A 保持机器建议与人类授权的区别，代价是每次正式纳入需要对固定依据作人审；不新增 `model_reviewer`，不接通运行命令。

本次纠正文档的四项过强推断：独立 root 下的多 attempt 并未被全局禁止；未验收、失败、unknown 与拒绝仍可成为账本事实；未采用包可留存不等于必须永久保留或正式纳入；`events_read` 已有序列游标增量，对象差异投影另待设计。方案评分、知识反馈积分与 skill 四维评价分别管理；skill 数据接口仍不接执行。不可变问答用回答引用问题及后续汇总关联，不能要求问题预先引用尚未发生的回答。

并行拆分的模块与同模块的替代实现是两种关系：可以按模块选择或明确组合实现，再固定多模块包清单并做集成验收，不要求全项目只选一包。方案评分需固定量表版本和同等评测条件；模块整理产生新版本后重新核对受影响的测试及批准依据。上述新增语义仍是设计，不把现有多 attempt 查询或目录隔离当作完整并行系统或 OS 沙盒。

### 选择的资料与限制

直接资料为本轮需求/任务、六份架构页（从 1.0.0 修为 1.1.0），以及 K-DELIVERY、K-EXECUTION、K-STORAGE、K-LEDGER、K-QUERIES 的节点。为核对身份和真实已有能力，读取直接相关 `policy.py`、`flow.py`、`attempt/service.py`、`delivery/service.py`、`queries/service.py`、`uow.py`、`records.py` 与 `knowledge/scoring.py` 的定向片段；源码基线为页头提交。没有加载全部历史证据、个人画像或其他会话，没有完成全面逐文件审查。

本次只做文档静态检查，未运行 Python/Node 行为测试、构建 wheel 或接入宿主。用户交接消息所称 620 项测试通过不是本次执行证据；路线 A 的文档确认也不是新运行能力验收。

### 合并后的独立复核与实际检查

源码复核代理另行检查合并后的六页、需求和任务记录，指出需求摘要不能把高聚合写成依赖图可直接算出的事实，也不能把尚待设计的收敛映射写成已确定交付；主代理已同步收窄。其余在该定向范围内未发现新的实质源码事实错误或路线 A、存储、增量读取和问答时序的跨页冲突。这不是全面源码审查。

最终只读静态核对结果：17 个本次文件、270 个 Markdown 本地链接目标、23 个模块节点，errors=[]。覆盖链接与标题锚点、架构页表格、版本、尾换行和尾空白、节点 ID/关系与无环导航、JSON 解析及 runtime/冻结文件范围。`git -c core.safecrlf=false diff --check` 退出 0；`git status --short -- src bridge tests contracts pyproject.toml` 无输出。没有提交、推送或发布。

## 详细架构复现规格（本轮版本 4）

用户要求架构记录详细到模型在没有本次聊天历史的情况下能从零复现，并增加架构图。交付为[R1 总指南](../../architecture/reproduction-blueprint.md)与[数据/事务](../../architecture/reproduction/01-data-and-transactions.md)、[编排/交互](../../architecture/reproduction/02-orchestration.md)、[上下文/数据处理](../../architecture/reproduction/03-context-and-evaluation.md)、[实施/验收](../../architecture/reproduction/04-build-and-acceptance.md)四章，对应 REQ-BOUNDARY-13。既有需求和路线 A 沿用，同轮更新，不另开需求轮次。

### 规格范围与分工

R1 为复现采用单项目 SQLite 中逻辑分层、单层 fan-out、显式类型与版本格式；这些是参考实现选择，物理分库和未来嵌套仍未替用户拍板。正文覆盖 schema 字段、DDL、幂等/CAS、不可变引用、基线/分支/多方案、制品与验收、评分、人类确认、SCM 效果后发布采用、上下文请求、模型与工具调用留存、实时表单和失败恢复，并列实施切片及待运行验收。未修改冻结 v1 或接通新运行接口。

三名代理分别编写数据、编排、上下文章节，主代理编写总指南与实施/验收章并维护索引。交叉审阅补齐初始 clarifying 基线 P0、完整项目验收项、明确 SCM 目标种类及远端映射、表单 schema 制品、模型原始响应与工具调用意图、索引重建水位变化时拒绝切换等细节。数据代理后续受外部模型服务额度错误中断，已写文件保留，由主代理接手检查和修正。

### 本段工具及代理错误分析

| 失败 | 原因与证据范围 | 影响、修正与验证 |
| --- | --- | --- |
| 初次代理读取 reproduction 目录不存在 | 上下文章节代理回报 rg 在并行写作尚未建立目录时返回 os error 2；路径属于计划新增目录，不是已有接口失效 | 随创建目标文件建立目录后正常读取；未写 runtime，无外部效果 |
| 测试目录检索路径通配符失败 | 主代理将 `tests/test_*.py` 作为 Windows rg 路径，返回 os error 123；PowerShell 不替本机程序展开该路径通配符 | 无写入；改为 `rg --files tests -g '*test*.py' -g '*test*.js'` 成功发现已有测试；没有运行这些测试 |
| 编排章补丁上下文不匹配 | 代理回报预期 Mermaid 旧文本与实际多出的状态行不符，apply_patch 未应用该补丁 | 重读实际图并拆小补丁完成；状态闭集再与数据章核对 |
| 数据代理模型服务拒绝继续 | collaboration 返回 HTTP 403，提供方响应明确标示预扣费额度不足；错误发生在代理后续模型请求，不是 Kernel/provider 运行 | 已写数据章保留；未反复重试同服务，由主代理接手；该代理不能完成的后续自检由主代理执行。除提供方返回的额度原因外，不推断账户或网络故障 |
| 批量文档读取输出截断 | 主代理工具返回 truncated output，合批总输出超过预算 | 关键规格改为分章/分段及符号读取；不将截断内容登记为全源码阅读 |
| 上下文章节静态脚本误拆表格 | 代理回报首版脚本以 Markdown 竖线拆字段，在 `string\|null` 类型处截断并抛出 AttributeError；属于自编检查器对代码跨度的解析不足 | 改为读取字段所在反引号跨度后复验成功；主代理最终同时核对表格转义与列数，不将脚本异常当运行功能失败 |

没有将这些工具或模型服务错误用于评分用户、降低 skill 方法分数或触发自动执行重试。运行时、测试、schema 和冻结材料的修改范围由最终检查核对。

用户报告死机后，主代理重新检查工作树并沿用已写入的五份规格，完成剩余校准。没有取得操作系统故障日志，不能判断死机根因，也不将其归因于内核、代理或文档；此项只记录用户报告和恢复动作。

最终文档检查还发现两处未转义竖线：数据章 TargetSpec 说明及本段失败表，导致 Markdown 表格多列。已分别改为文字表达和转义，再检查列数；问题只影响文档呈现，不涉及运行数据或外部效果。

### 本段最终检查与交付限度

五份 R1 规格合计 1792 行，包含 22 个 Mermaid 图块、9 个 JSON 示例、5 段 Python 伪代码、19 张参考 SQLite 表和连续编号的 33 项 R1-AC 待运行条件。对本段涉及的 21 个文件执行只读核对：462 个本地链接及锚点、表格列数、代码围栏、版本、单尾换行与行尾空白均无错误；23 个模块节点的 ID、关系和导航无环，模块及 skill registry 可解析。

JSON 示例均通过解析，Python 伪代码通过 AST 语法检查；参考 DDL 在内存 SQLite 成功执行，外键定义检查无错误。这些是文档示例的检查，不是 R1 运行系统或业务场景验收。Mermaid 检查覆盖图块围栏与声明，并人工核对了组件、状态及步骤；本环境未提供 Mermaid 渲染器，未做渲染或布局验收。

`git -c core.safecrlf=false diff --check` 退出 0；runtime、bridge、tests、冻结 contracts 及 pyproject 的状态查询无改动。保留工作树中前段已有文件和修改，没有提交、推送、部署、真实模型/宿主/SCM 接入或行为测试。所有 R1-AC 条件保持 not_run，`release_approved=false`。三名代理的规格编写与定向独立复核帮助修正字段和时序，并不证明另一个实施模型已按本文完成系统；真正从零实现的复现结果需后续实施证据。

## 修订记录

| 记录版本 | 更新时间 | 内容 |
| --- | --- | --- |
| 1 | 2026-10-12 | 建立本轮边界需求与静态核对任务记录 |
| 2 | 2026-10-12 | 追加执行流、并行分支与存储分层需求（REQ-BOUNDARY-06~11） |
| 3 | 2026-10-12 | 确认路线 A 并校正执行流映射措辞 |
| 4 | 2026-10-12 | 建立 R1 从零复现规格与实施要求（REQ-BOUNDARY-13） |
| 5 | 2026-10-13 | 同日会话总结：确认执行流与双层存储思路，归档未决项（无新实现或验收） |
