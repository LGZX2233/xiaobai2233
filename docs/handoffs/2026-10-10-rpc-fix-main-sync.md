# RPC 修复主分支同步记录

日期：2026-10-10（Asia/Shanghai，日期精度）。用户已授权修复 RPC、更新文档并提交推送；原“不运行测试”要求继续有效。范围为独立仓库 `kernel_next`，远端为 `https://github.com/LGZX2233/xiaobai.git`。

| 项目 | 已核对结果 |
| --- | --- |
| 修复前源码 | `0a619766162682606ad57a9aa4c1926d54c1b891` |
| RPC 修复与前期维护提交 | `c36453981a2151c7652b54301c0cb5a7a1840856`，67文件变更，包含两个 RPC 文件、文档、技能及测试路径迁移 |
| 读取时远端 main | `b665512e0718027375198e5026389970a230aacb`；其新增两个 README 提交均保留 |
| 合并提交 | `dd502cef0c52ca82db40e25fb5a209807bd2ad76`；两侧历史保留，仅 README 冲突人工解决，保留仓库名 xiaobai2233 与内核入口 |
| 普通推送 | `git push origin main` 成功，远端从 b665512 快进至 dd502ce，没有强推 |
| 独立远端核对 | `git ls-remote --heads origin main` 返回完整 dd502ce，与本地 HEAD 和 origin/main 相同 |
| 本地分支 | 原工作分支改名为 main，跟踪 origin/main；未推送新的功能分支 |
| 初次推送后工作区 | `git status --short` 无输出 |

## 后续文档交付

本记录与版本字段、任务完成状态随后提交为 `62bb5d7263d03cd3d6557636503d1a1b7383c6b5`（`docs: record RPC fix and verified main synchronization`），已普通推送到 main。Git 远端成功回执为 `dd502ce..62bb5d7 main -> main`；随后本地 HEAD 与 origin/main 均为完整62bb5d7，工作区干净。

此前推送后的独立 `ls-remote` 与 `push --dry-run` 读取因 GitHub 连接失败未完成。本轮描述修订时再次以 HTTP/1.1 执行 `git ls-remote --heads origin main`，成功返回完整62bb5d7，与本地 HEAD 和 origin/main 一致；因此该文档交付现有成功推送回执及独立远端读取两项证据。上表仍保留初次核对的 dd502ce 快照。

用户随后要求补齐 Markdown 描述，本轮更新 README、现状及相应记录，RPC 源码版本仍为 c364539。本轮生成的提交由 Git 历史定位，本记录不预填自身提交 SHA。

同步资料提交前，8份变更/新增 Markdown 的121个本地目标、2个标题锚点及格式核对通过，JSON 可解析，`git diff --check` 通过；再次核对53项保护摘要一致，源码无追加变化。

验证范围是[RPC 任务](../records/tasks/2026-10-10-rpc-resilience.md)记录的静态代码审阅、AST、文档链接、索引、保护摘要和 Git 差异检查，没有测试或行为探针。合并未改变两个 RPC 文件；53项保护文件仍保持原字节，G2 继续 `accepted_g2`、`release_approved=false`。

普通合并时 Git 报告既有证据路径超过 Windows 默认长度；启用此仓库 `core.longpaths=true` 后确认只有 README 冲突，无证据修改。沙箱网络的 localhost 代理使远端访问失败，按工具权限要求在宿主网络执行读取和推送；未绕过测试、Git hook 或产品沙箱。

knowledge 提升仍未接入核心 RPC，其授权和效果顺序缺口保留为后续事项。本次主分支同步不代表生产发布批准。
