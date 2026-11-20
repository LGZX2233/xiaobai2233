# 本地 MCP 接入

按首页安装后，在宿主控制的绝对路径保存 JSON 配置。以下 PowerShell 命令在当前目录创建独立测试配置和新的数据库路径。

```powershell
$config = @{
  store_path = (Join-Path $PWD 'demo.sqlite')
  project_id = 'local-project'
  store_id = 'local-store'
  principal = 'local-agent'
  capabilities = @('project.read', 'design.write')
  mode = 'test'
}
[System.IO.File]::WriteAllText((Join-Path $PWD 'host.json'), ($config | ConvertTo-Json))
```

在支持 stdio 的 MCP 客户端配置中，将 command 设为虚拟环境中 python.exe 的绝对路径。args 依次为 `-B`、`-m`、`project_kernel.interfaces.headless.mcp`、`--config` 和 host.json 的绝对路径。连接后执行 MCP initialize 和 tools/list。实际工具随所授能力与配置变化。由可信宿主管理配置与 stdio 管道访问权；人类确认操作需要相应的人类入口。

工具写入前读取目标版本。发生过期冲突时重新读取记录并核对最新依据。写入结果未知时根据原幂等键核对回执。冻结 v1 信封与示例在 contracts/v1 目录。

## DSH 桌面工作台

保留 ZIP 解压后的目录结构。在 DSH 的 Cordis 插件配置中，将项目原生工具指向 `project-package/extensions/dsh-kernel-frontend/native-tools.mjs`，工作台指向 `project-package/extensions/dsh-kernel-frontend/workbench/index.mjs`。两个插件的入口均使用解压后的绝对文件 URI。两个配置使用相同的 `repoRoot`（解压根目录）、`pythonExecutable`（已安装 wheel 的虚拟环境解释器）和 `projectDataRoot`（宿主控制且可写的项目数据目录），并设置 `enabled: true`。

重载宿主后，从 DSH 原生项目入口登记或打开项目，再从工作台首页打开版本管理。桌面插件会经已认证资源路由加载 Hannes 共享客户端。Hannes 独立宿主使用 `project-package/extensions/hannes-workbench/package.json` 的导出入口，需要 Node 24.10 或更新版本。
