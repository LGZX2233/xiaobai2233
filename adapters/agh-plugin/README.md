# Project Kernel 的 AGH 插件（0.3.1）

这个插件把 Project Kernel 的“机器通道”以智能体工具的形式交给 AGH（Agnes Harness）里的模型，并给浏览器侧边栏提供 13 个只读查询服务（`pk.*`）和一个 React 面板。模型负责规划、调用工具和决策；内核只负责记录和校验，不做规划。

内核状态口径：历史核心状态为 `accepted_g2`，`release_approved=false`。本插件不改变这个状态，也不构成新的验收或发布。

## 它是怎么连起来的

```
AGH 里的模型 ──调用工具──> index.mjs（本插件）──stdio JSON-RPC──> Python 内核宿主（tests/p14_science_demo/agh_host.py）
                                                                    └─ 不可变 SQLite 账本
人（终端里）──tools\pk-human-approve.ps1──> 同一个 SQLite 账本（人工通道，不经过插件）
```

- 插件和内核只通过 stdio 上的 JSON-RPC 通信（换行分帧）。这不是 MCP。
- 宿主进程只有机器通道，没有人工审批入口；`approval.decide` 在机器通道上会返回 `UNSUPPORTED_COMMAND`（测试 `tests/p14_science_demo/test_heat_inversion_flow.py` 覆盖）。
- 演示场景：一维热传导反问题，反演扩散系数 alpha（真值 0.37，容差 5%）。数据是合成且确定性的；证据模式是 `test`；隔离方式是 `directory_only`（目录级隔离，不是操作系统沙箱）。

## 找到内核的顺序

AGH 会把已安装的包复制到自己的包缓存里，所以插件目录只是最后的备选。顺序是：

1. 环境变量 `PK_KERNEL_ROOT`（指向 `kernel_next` 目录）。设置了但路径不对时直接报错，不会再往下找。
2. AGH 守护进程的当前目录（cwd），要求其中有 `tests/p14_science_demo/agh_host.py` 和 `src/project_kernel`。
3. 插件目录往上两级（在仓库里直接运行时）。

找不到时，工具会返回 `KERNEL_NOT_FOUND` 和该设置什么。`tools\start-agh.ps1` 会替你设好 `PK_KERNEL_ROOT` 和 `PK_PYTHON`。

## 环境变量

| 变量 | 作用 | 默认 |
|---|---|---|
| `PK_KERNEL_ROOT` | 内核仓库（`kernel_next`）位置 | 见上面的查找顺序 |
| `PK_PYTHON` | 运行宿主的 Python | 仓库 `.venv`（Windows 为 `.venv\Scripts\python.exe`），否则 `python` |
| `PK_HOST_SCRIPT` | 宿主脚本 | `<内核仓库>/tests/p14_science_demo/agh_host.py` |
| `PK_ROOT` | 本次运行的数据目录 | 系统临时目录下 `pk-agh-demo-<时间戳>`；宿主要求它在系统临时目录或 `.validation-tmp` 之下 |
| `PK_REGISTRY` | 模块登记表（面板“结构”用） | `<内核仓库>/docs/modules/registry.json` |
| `PK_SKILLS_REGISTRY` | 技能登记表 | `<内核仓库>/docs/records/skills/registry.json` |
| `AGH_ROOT` | 构建面板和跑测试时找 esbuild、React 的位置 | `D:/bisai/agnes-harness-main`（见 `scripts/dependencies.mjs`） |

第一次调用任意工具时才会启动 Python 宿主；之后会把本次数据目录写到临时目录的 `pk-agh-last-root.txt`，人工审批脚本用它找到同一个账本。

## 智能体工具

| 工具 | 参数 | 作用 |
|---|---|---|
| `pk_state` | 无 | 看任务、策略 s1/s2/s3、环境检查和流程指引（从这里开始） |
| `pk_run_strategy` | `strategy_id` | 把一个策略作为新尝试运行。s1 粗网格，s2 黄金分割，s3 会卡住并落为 `unknown`，保留且不重跑 |
| `pk_verify` | `strategy_id` | 对已完成的策略做独立校验，返回 `passed`、原因和 `alpha_fit`；对 `unknown` 的尝试返回 `skipped`，不报宿主错误 |
| `pk_compare` | 无 | 列出全部尝试，失败和 unknown 都保留 |
| `pk_select` | `strategy_id`、`reason` | 选择要交付的策略并写明理由；对比范围默认是全部尝试 |
| `pk_request_delivery` | 无 | 申请交付，产生一个待人工审批的 approval；之后必须停下等人 |
| `pk_apply_delivery` | 无 | 人批准之后应用交付；没批准时内核拒绝，并提示去终端审批 |
| `pk_events` | 可选游标 | 读审计事件（按提交顺序） |

工具参数都是短 id（`s1` 等）。需要内核对象引用的地方，插件在会话里记住了上一步的结果，模型不必复制 JSON；旧的完整引用参数仍然可用，但一般不要填。工具里没有任何审批或决定类的工具，测试里有断言（`test/tools.test.mjs`）。

## 人工审批

模型不能批准。批准发生在终端里，由人亲自完成：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\pk-human-approve.ps1
```

脚本列出待审批的交付（选中的策略、alpha_fit、证据模式、快照摘要），人核对后输入快照摘要的前 8 位十六进制字符才会批准；输入 `r` 并写理由则拒绝。实现在 `tools/pk_human_approve.py`：

- 没有终端（TTY）就拒绝运行；这个检查和输入摘要前缀是“有人在终端前看过这份快照”的交互证明，**不是安全边界**，能在本机运行命令的人同样可以直接调用 `decide()`。
- 通过 `build_human_server` 加 `InteractionProof("terminal-typed-digest-prefix", True)` 签发人工句柄，模式为 `test`。
- 非交互核心 `decide(root, approval_id, digest_prefix, decision, reason)` 供测试和演练脚本使用；测试 `test_human_approve_cli.py` 在 AGH 宿主进程还开着同一个账本时调用它（SQLite WAL 加共享访问栅栏允许并发）。

批准后回到 AGH 对智能体说“已批准”，它再调用 `pk_apply_delivery`。

## 安装与启动（Windows PowerShell 5.1）

在仓库根目录 `D:\deepseekhannes\kernel_next` 里，每步一条命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\install-agh-plugin.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tools\start-agh.ps1
```

- `install-agh-plugin.ps1`：设置 `AGH_HOME` 和 `AGNES_PROFILE=local-dev`；先 `package disable`、`remove` 旧版本（没装过就忽略）；再执行 `package add file:./adapters/agh-plugin`。AGH 只有在标准输入输出都是终端时才会问 `Install <id>@<version> (<integrity>)? [y/N]`，所以这一步请在你自己的 PowerShell 窗口里输入 `y` 再回车。之后脚本从 `operations.json` 读出本次安装的 integrity 和 capabilityHash，执行 `trust`、`enable`、`status`。找不到本次的记录时会停下，不会用旧记录去信任。
- `start-agh.ps1`：设置 `AGH_HOME`、`AGNES_PROFILE`、`PK_KERNEL_ROOT`、`PK_PYTHON`，进入仓库根目录，运行 `node <runtime> serve --port 5186`。端口被占用时只打印占用进程号和 `Stop-Process -Id <进程号>` 命令，不会替你结束进程。浏览器打开 `http://127.0.0.1:5186/`。
- 默认路径：运行时 `D:\bisai\agh-build\runtime\agnes.mjs`，`AGH_HOME` 为 `D:\bisai\kernel-agh-work\agh-native-17e504be-56d6-4f89-aaa3-b69eda1b3a3c`，都可以用 `-Runtime`、`-AghHome` 改。
- 这些脚本已用 PowerShell 7 的语法解析器检查过（0 个语法错误）；在 Windows PowerShell 5.1 里的实际运行、AGH 的 `[y/N]` 提示和端口检查，需要在你的机器上走一遍才能确认。

## 构建、测试

```bash
# Python（在仓库根）
python -m pytest -q tests/p14_science_demo tests/p15_innovation_showcase
# Node（在 adapters/agh-plugin，设置 AGH_ROOT、PK_PYTHON 后）
node --test test/*.test.mjs
# 面板构建
node scripts/build.mjs
```

## 诚实的限制

- 演示宿主放在 `tests/p14_science_demo/` 而不是 `src/`：它需要只在测试里才有的播种辅助（`p02_design.helpers`）。所以插件要求完整的内核源码树；只拷插件目录是不够的。
- 内核和插件之间只有 stdio JSON-RPC，不是 MCP；宿主不对外开放网络端口。
- 只在 AGH 上验证过；没有在其他智能体平台上试过。
- 隔离是目录级（`directory_only`），不是操作系统沙箱；证据模式是 `test`，数据是合成的。
- 模型和提示词的表现会变化：`evidence/rehearsal/` 里是两个模型在 AGH 之外直连接口的演练（同一组工具、同一个内核），每个模型各两次，不是 AGH 里的运行，也不是统计结论。
- 面板和服务的说明见 [执行规格](docs/frontend-design.md) 与 [任务记录](../../docs/records/tasks/2026-10-13-agh-frontend.md)；开发用的 profile 在 [docs/local-dev.profile.yaml](docs/local-dev.profile.yaml)（需要 `services` 能力上限）。
