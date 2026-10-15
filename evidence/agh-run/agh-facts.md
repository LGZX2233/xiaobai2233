# AGH 环境与工作目录事实（沙箱实测 + 源码引用）

测试环境：官方 AGH 打包运行时（`agh 0.0.0 node 24.22.0 protocol _agnes/v1`，Linux 沙箱），源码对照 `agnes-harness-main`。
所有结论标注来源：**实测**（本次运行的进程快照）或**推断**（只读源码得出，未单独验证）。未在 Windows 上验证。

## 1. 谁运行插件
- **实测**：进程树为 `daemon.mjs`（pid 22）→ `worker.mjs`（pid 89，`AGNES_WORKER_KIND=session`）→ `python -I -B -X utf8 …/tests/p14_science_demo/agh_host.py --root …`（pid 296，父进程是 worker 89）。也就是说插件的 `index.mjs` 在 **会话 worker 进程** 里执行，内核 Python 宿主是 worker 的子进程；不是 daemon 直接执行。
- 代码：`adapters/agh-plugin/kernel-session.mjs:31`（spawn Python）、AGH `packages/daemon/src/supervisor/worker-pool.ts:448-449`（worker 的 env = `...process.env` + `AGH_HOME`）。

## 2. 插件能不能看到 PK_KERNEL_ROOT / PK_PYTHON / PK_ROOT 和 cwd
- **实测**（在仓库目录里先 `export PK_KERNEL_ROOT PK_PYTHON PK_ROOT`，再启动 AGH）：daemon、worker、Python 宿主三个进程的环境里都有 `PK_KERNEL_ROOT`、`PK_PYTHON`、`PK_ROOT`、`TMPDIR`、`AGH_HOME`；daemon 和 worker 的 cwd 都是 `--cwd` 指定的仓库目录。`pk_state` 返回的 `pk_root` 与导出的 `PK_ROOT` 一致。
- 代码：AGH `packages/cli/src/boot/backend.ts:260-266`（`launchWorkspace`：daemon 的 workspace = `--cwd`/当前目录）、`:285-296`（daemon 以 `...process.env` 启动，cwd = workspace）。
- **推断（未单独验证）**：daemon 是常驻、被后续命令复用的。环境变量在 **daemon 第一次启动时** 固定；之后在别的终端里再 `export` 不会被已运行的 daemon 看到。所以 Windows 上要先设好变量，再第一次启动 AGH（或先停掉旧 daemon）。

## 3. 插件怎么找内核目录（发现顺序）
`adapters/agh-plugin/index.mjs:29-63` `resolveKernelPaths`：
1. `PK_KERNEL_ROOT`（`:36-40`，路径无效时直接报错，不回退）；
2. 否则 daemon 的 `cwd`（`:41-42`）；
3. 否则插件目录的 `../..`（`:43-44`）；都不对则报 `KERNEL_NOT_FOUND`（`:45-49`）。
Python：`PK_PYTHON` → `<kernel>/.venv/(Scripts|bin)/python` → `python`（`:50-52`）。运行目录：`PK_ROOT`，否则 `<tmp>/pk-agh-demo-<时间戳>`（`:60`）。
`defaults` 在模块加载时一次性计算（`:65-67`，用 `process.env` 与 `process.cwd()`），所以改环境变量要重启 worker/AGH 才生效。

## 4. 已安装的插件副本在哪
- **实测**：`<AGH_HOME>/data/profiles/local-dev/packages/@project-kernel__agh-plugin/`（安装时 AGH 复制了一份，含 `index.mjs`、`client/`、`vendor/`）。因此第 3 点里的“插件目录 `../..`”在安装后指向这份缓存副本的上两级，**不是**仓库；真正可靠的是 `PK_KERNEL_ROOT` 或从仓库目录启动。

## 5. 其他实测约束（影响安装说明）
- `tests/p14_science_demo/agh_host.py:149-151`：`PK_ROOT` 必须位于 `.validation-tmp` 或系统临时目录下。沙箱里 `TMPDIR` 被指到别处，导致 `HOST_EXITED`，必须 `TMPDIR=/tmp`；Windows 默认 `%TEMP%` 没有这个问题（未验证）。
- `agh -p` 在 stdin 不是终端时会读 stdin 直到 EOF（AGH `packages/cli/src/modes/prompt-input.ts:28`），脚本里要写 `< /dev/null`。
- `agh package add` 只有 stdin 和 stdout 都是终端时才会问 `[y/N]`（`packages/cli/src/bin.ts:879` 附近），非交互环境要用伪终端（`tools/agh-sandbox/install_plugin.py`）。
- 要让右侧面板出现，插件后端必须已被某个会话启动过（名册状态从 `blocked/backend-revision-unavailable` 变为 `ready`）；全新 AGH 第一次打开页面时看不到 PK 启动器，发一条任意消息后刷新页面即可。
- 无头模式（`agh -p`）没有批准提示器，`pk_request_delivery`（`requiresApproval: always`）会被直接拒绝为 `APPROVAL_REJECTED`；要走网页或 TUI。
