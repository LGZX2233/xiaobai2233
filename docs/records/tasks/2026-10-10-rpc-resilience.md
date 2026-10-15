---
record_id: RPC-TASK-20261010
record_version: 4
updated_at: 2026-10-10
timezone: Asia/Shanghai
source_revision: c36453981a2151c7652b54301c0cb5a7a1840856
source_worktree: README and current descriptions corrected after pushed documentation 62bb5d7; RPC source unchanged
status: completed_pushed
requirement_ids: [REQ-RPC-01, REQ-RPC-02, REQ-RPC-03, REQ-RPC-04, REQ-RPC-05]
module_ids: [K-RPC, K-ROOT, K-RECORDS]
acceptance_status: not_behaviorally_validated
---

# 2026-10-10 RPC 修复与主分支交付

本次将过深 JSON、未配对 Unicode 和响应编码异常收口到协议错误，并更新阅读入口和问题状态。[需求](../../requirements/2026-10-10-rpc-resilience.md)拥有修复判据；[原审查](../../reviews/2026-10-10-design-review.md)保留修复前发现。

## 代码与设计

| 改动 | 当前处理 |
| --- | --- |
| [framing.py](../../../src/project_kernel/interfaces/rpc/framing.py) | 解析递归异常转 `FrameError`；迭代验证所有解码字符串能 UTF-8 编码，包括 dict keys；响应序列化的 TypeError、ValueError、RecursionError 转稳定 `FrameError` |
| [protocol.py](../../../src/project_kernel/interfaces/rpc/protocol.py) | 在分发前选择符合冻结正则的安全 id；原请求仍按 Schema 校验；编码失败返回仅含安全 id 的 Internal error；兜底再次失败使用固定 ASCII、null id 的错误 |

深度策略采用 Python JSON 解码器当前递归上限，不另设永久深度常量。合法 Unicode 字符及由 JSON 解码器合成的非 BMP 字符保持可用；未配对代理码输入统一返回解析失败 `-32700`。原大帧响应继续使用既有 `CAPABILITY_UNAVAILABLE` 结果，其他响应编码失败为 `-32603`。

安全 id 复用冻结正则的匹配语义，包括其既有锚点行为，避免静默加严后将原可接受请求的 id 变成 null。非法 id 仅在响应中变成 null，原请求字段不被修改，不能因此通过原 Schema 校验。

## 文档与上下文

修改前读取 K-RPC、原审查、冻结 initialize/command/query 的 id 规则、framing/protocol 实现和现有测试源码。直接依赖仅核对 K-CONTRACTS 的协议规则；本次没有更改身份、账本或业务 provider。knowledge 提升仍是未接线的后续问题，没有读取全量验收输出或建立对话映射。

沿用项目 `kernel-maintain-records` 2.0.0，维护当前节点、问题索引和项目摘要；本次真实使用另记[方法观察](../skills/2026-10-10-maintain-records-rpc-use.md)。按用户指定的 `gpt-6.1-sol` 分发只读静态代码复核和文档修订。代码复核未发现实质缺陷；没有测试、探针或项目运行。

## 验证与 Git 状态

| 核对 | 实际结果 |
| --- | --- |
| 源码静态复核 | gpt-6.1-sol 只读审阅两个 RPC 文件的调用链及差异，未发现实质缺陷；非法 Unicode 统一解析失败是预期策略 |
| 语法 | `.venv/Scripts/python.exe -B` 用 AST 解析两个变更文件通过；没有导入或运行项目代码 |
| 文档 | 提交前58份新增/变更 Markdown，689个本地目标、18个标题锚点有效；末尾单换行及尾空白通过 |
| 索引 | 23节点关系与机器索引一致，导航无环、目标存在、对话关联为空；2个 skill 版本及证据引用有效 |
| 保护输入 | 53项 protected-inputs 的 SHA256 全部相同；没有修改冻结 Schema、fixtures、旧接受记录、原始证据或既有 ZIP |
| 历史 manifest | 1281项中四个旧测试路径已迁移，八个既有文件摘要变化；含此前六项维护文件及本次两个 RPC 文件；未重建历史 manifest |
| 工作目录 | 功能源码缓存为空；运行目录仅修改 framing.py 和 protocol.py |
| Git 差异 | 首次提交前 `git diff --check`、`git diff --cached --check` 通过；随后普通提交、合并和推送结果见下方 |

用户之前“不用测试了”的要求继续有效；没有运行 Python/Node 测试、复现输入、宿主或 G2 重建。文档状态不表示新的行为接受。

修复前源码为 `0a619766162682606ad57a9aa4c1926d54c1b891`；修复及前期维护已提交为顶部 c364539。远端 main 读取时为 `b665512e0718027375198e5026389970a230aacb`，其新增两个 README 提交通过普通合并保留。合并提交 `dd502cef0c52ca82db40e25fb5a209807bd2ad76` 已普通推送至 main，并通过独立远端读取核对一致；初次推送后工作区干净。README 保留仓库名与内核入口，本地分支为 main 并跟踪 origin/main。

[主分支同步记录](../../handoffs/2026-10-10-rpc-fix-main-sync.md)保存初次独立读取核对的 dd502ce 快照，以及后续文档提交 `62bb5d7263d03cd3d6557636503d1a1b7383c6b5` 的成功推送回执。该次推送后本地 HEAD 与 origin/main 均为62bb5d7，工作区干净；当时独立远端读取因连接失败未完成。本轮描述修订前再次独立读取 main 成功，返回完整62bb5d7，与本地引用一致。

本次同时收入此前获授权的[模块与持续记录工作](2026-10-10-kernel-maintenance.md)及[布局和技能成长](2026-10-10-layout-and-skill-growth.md)。那些任务中的未提交、未推送描述是对应阶段的事实，当前结果由本任务及后续同步记录拥有。

knowledge 提升缺口仍未修复且不在核心 RPC 入口。生产发布许可、G3/G4 和生产部署状态没有因本次提交改变。

## Markdown 描述补充

用户在交付后明确要求“把描述也更新了啊，md”。README 原先将 RPC 状态放在末尾，并让读者跳到任务记录寻找交付结果；本次把项目用途、G2 历史接受、已交付能力、RPC 修复与文档维护区别写入主要阅读路径，同时更新现状、项目总结、审查摘要和同步记录。运行源码没有追加改动，历史审查动作和冻结接受资料没有改写。

上下文采用 README、内核现状、K-ROOT/K-RPC、当前任务/项目总结及同步记录；记录维护方法的本次反馈见[方法观察](../skills/2026-10-10-maintain-records-rpc-use.md)。验证范围仍为本地 Markdown 链接、元数据和 Git 差异，不运行测试或行为探针。本次描述修订的提交 SHA 由 Git 历史定位。

本次7份 Markdown 的83个本地目标、2个标题锚点、版本字段与末尾换行核对通过，53项保护文件的 SHA256 全部相同，`git diff --check` 通过。另按用户指定以 `gpt-6.1-sol` 只读审阅描述差异及历史数字来源，未发现实质问题；没有运行项目代码。

## 修订记录

| 记录版本 | 日期 | 内容 |
| --- | --- | --- |
| 1 | 2026-10-10 | 记录 RPC 修复、静态复核、上下文和获授权提交范围，待整合核对及 Git 交付 |
| 2 | 2026-10-10 | 源码与文档静态核对完成，准备普通提交及主分支同步，行为验证仍未执行 |
| 3 | 2026-10-10 | 记录 c364539 修复、dd502ce 普通主分支推送与远端核对；追加同步资料，行为验证仍未执行 |
| 4 | 2026-10-10 | 根据用户反馈补齐 Markdown 主要描述，补记62bb5d7推送及本轮独立远端读取成功 |
