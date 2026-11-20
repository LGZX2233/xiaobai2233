# Windows x64 发行说明

使用 Windows x64 和 64 位 CPython 3.12。从同一 Release 下载 [Windows x64 ZIP](https://github.com/LGZX2233/xiaobai2233/releases/download/v0.50.0/xiaobai-v0.50.0-win-x64.zip) 与 [SHA256SUMS.txt](https://github.com/LGZX2233/xiaobai2233/releases/download/v0.50.0/SHA256SUMS.txt)，在 PowerShell 运行 `Get-FileHash ./xiaobai-v0.50.0-win-x64.zip -Algorithm SHA256`，核对清单中同名文件的摘要。打开一个新虚拟环境，在 ZIP 所在目录运行以下三行。

```powershell
Expand-Archive ./xiaobai-v0.50.0-win-x64.zip ./xiaobai-v0.50.0-win-x64
cd ./xiaobai-v0.50.0-win-x64
python -m pip install "project_kernel-0.50.0-cp312-cp312-win_amd64.whl[mcp]"
```

在解压目录也可用随包提供的 `./install.ps1` 完成第三步，它会核对环境和 wheel 摘要，再安装 MCP 依赖并执行 `pip check`。

如需指定解释器，可在解压目录运行 `./install.ps1 -Python 'C:/path/to/venv/Scripts/python.exe'`。pip 需要能取得 MCP 依赖。Windows 发行包内提供 Hannes、DSH、Node 协议桥和 CPython 原生 wheel。编译版使用条件详见 ZIP 内的 `RELEASE-LICENSE.txt`，本公开仓的契约、Skill 和文档使用 [MIT](../LICENSE)。

产品发行号为 0.50.0，冻结 v1 协议号为 1.0.0。[发行资产](https://github.com/LGZX2233/xiaobai2233/releases/tag/v0.50.0) · [验收回执](https://github.com/LGZX2233/xiaobai2233/releases/download/v0.50.0/RELEASE-VERIFY.json) · [接入 MCP 与 DSH](integration.md)
