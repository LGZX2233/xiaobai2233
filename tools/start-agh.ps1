<#
  start-agh.ps1  启动 AGH 网页界面（Windows PowerShell 5.1）

  作用：设置好环境变量（让插件找到项目内核和 Python），检查端口，然后在前台启动 AGH。
        启动后用浏览器打开 http://127.0.0.1:5186/ 即可。

  运行方式（Windows 默认禁止直接运行 .ps1，请在仓库目录里粘贴下面这一行）：
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\start-agh.ps1

  想换端口：
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\start-agh.ps1 -Port 5187

  停止：在本窗口按 Ctrl+C，或直接关闭本窗口。
  本脚本不会替你结束任何进程；端口被占用时只会告诉你该运行什么命令。
#>
param(
    [string]$Runtime = 'D:\bisai\agh-build\runtime\agnes.mjs',
    [string]$AghHome = 'D:\bisai\kernel-agh-work\agh-native-17e504be-56d6-4f89-aaa3-b69eda1b3a3c',
    [int]$Port = 5186,
    [string]$Node = 'node'
)

$ErrorActionPreference = 'Continue'

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
$RepoRoot = Split-Path -Parent $ScriptDir

$RunCommand = 'powershell -NoProfile -ExecutionPolicy Bypass -File tools\start-agh.ps1'
$InstallCommand = 'powershell -NoProfile -ExecutionPolicy Bypass -File tools\install-agh-plugin.ps1'
$AghProfile = 'local-dev'
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'

function Stop-WithError {
    param([string[]]$Lines)
    Write-Host ''
    foreach ($line in $Lines) { Write-Host $line -ForegroundColor Red }
    exit 1
}

# 从 netstat -ano 的输出里找出监听指定端口的进程号；找不到返回 $null。
# 行格式：  TCP    127.0.0.1:5186    0.0.0.0:0    LISTENING    1234
# 不依赖状态单词（中文系统可能本地化），只看「远端地址是 :0」。
function Find-ListenerPidInNetstat {
    param([string[]]$Lines, [int]$Port)
    foreach ($line in $Lines) {
        if ($line -match '^\s*TCP\s+\S+:(\d+)\s+(?:0\.0\.0\.0|\[::\]|\*):(?:0|\*)\s+\S+\s+(\d+)\s*$') {
            if ([int]$Matches[1] -eq $Port) { return [int]$Matches[2] }
        }
    }
    return $null
}

# 返回占用端口的进程号；没人占用返回 $null。先用 Get-NetTCPConnection，失败再退回 netstat。
function Get-PortOwnerPid {
    param([int]$Port)
    $cmdletWorked = $false
    try {
        $conn = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
        $cmdletWorked = $true
        if ($conn.Count -gt 0) { return [int]$conn[0].OwningProcess }
    } catch {
        $cmdletWorked = $false
    }
    if ($cmdletWorked) { return $null }
    try {
        $lines = @(netstat -ano)
        return (Find-ListenerPidInNetstat -Lines $lines -Port $Port)
    } catch {
        return $null
    }
}

# ---- 1. 检查文件 ----
Write-Host ''
Write-Host '[1/4] 检查文件' -ForegroundColor Cyan
Write-Host ('  仓库目录：' + $RepoRoot + '（脚本会切换到这里再启动 AGH）')

if (-not (Test-Path -LiteralPath $Runtime)) {
    Stop-WithError @(
        '未完成：找不到 AGH 运行文件 agnes.mjs。',
        ('  期望位置：' + $Runtime),
        '下一步：确认 AGH 已经构建好；如果它在别的位置，请指定完整路径重试：',
        ('  ' + $RunCommand + ' -Runtime "agnes.mjs 的完整路径"')
    )
}
if (-not (Test-Path -LiteralPath $Python)) {
    $fix = 'cd "' + $RepoRoot + '"; py -3.12 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e .'
    Stop-WithError @(
        '未完成：找不到项目的 Python 环境，AGH 插件需要它来运行项目内核。',
        ('  缺少文件：' + $Python),
        '下一步：复制下面这一整行，粘贴到 PowerShell 里回车（需要已安装 Python 3.12，安装过程要联网）：',
        ('  ' + $fix),
        '然后再运行：',
        ('  ' + $RunCommand)
    )
}
if (-not (Get-Command $Node -ErrorAction SilentlyContinue)) {
    Stop-WithError @(
        ('未完成：找不到 Node.js（命令 ' + $Node + '）。AGH 需要 Node.js 24 或更新版本。'),
        '下一步：安装 Node.js 24 后重新打开 PowerShell；或者如果你已经有 node.exe，指定它的完整路径：',
        ('  ' + $RunCommand + ' -Node "C:\...\node.exe"')
    )
}
$nodeVersion = ''
try { $nodeVersion = (& $Node --version | Select-Object -First 1) } catch { $nodeVersion = '' }
if (-not $nodeVersion) {
    Stop-WithError @(
        ('未完成：运行「' + $Node + ' --version」没有得到版本号，这个 Node 不能用。'),
        '下一步：安装 Node.js 24，或用 -Node 指定正确的 node.exe 完整路径。'
    )
}
Write-Host ('  Node 版本：' + $nodeVersion)
if ($nodeVersion -match '^v?(\d+)\.' -and [int]$Matches[1] -lt 24) {
    Write-Host '  提醒：AGH 要求 Node.js 24 或更新，当前版本偏旧，启动失败时请先升级 Node。' -ForegroundColor Yellow
}

# ---- 2. 环境变量 ----
Write-Host ''
Write-Host '[2/4] 设置环境变量' -ForegroundColor Cyan
$env:AGH_HOME = $AghHome
$env:AGNES_PROFILE = $AghProfile
$env:PK_KERNEL_ROOT = $RepoRoot
$env:PK_PYTHON = $Python
Set-Location -LiteralPath $RepoRoot
Write-Host ('  AGH_HOME       = ' + $env:AGH_HOME)
Write-Host ('  AGNES_PROFILE  = ' + $env:AGNES_PROFILE)
Write-Host ('  PK_KERNEL_ROOT = ' + $env:PK_KERNEL_ROOT)
Write-Host ('  PK_PYTHON      = ' + $env:PK_PYTHON)
if (-not (Test-Path -LiteralPath $AghHome)) {
    Write-Host '  提醒：AGH_HOME 目录还不存在，AGH 会新建一个空的；之前装的插件不会出现在里面。' -ForegroundColor Yellow
    Write-Host ('  如果这不是你想要的，请核对路径，或先运行：' + $InstallCommand) -ForegroundColor Yellow
}

# ---- 3. 检查端口 ----
Write-Host ''
Write-Host ('[3/4] 检查端口 ' + $Port) -ForegroundColor Cyan
$ownerPid = Get-PortOwnerPid -Port $Port
if ($null -ne $ownerPid) {
    $procName = '未知'
    try {
        $proc = Get-Process -Id $ownerPid -ErrorAction Stop
        $procName = $proc.ProcessName
    } catch { $procName = '未知（可能没有权限查看）' }
    Write-Host ''
    Write-Host ('未启动：端口 ' + $Port + ' 已经被占用。') -ForegroundColor Red
    Write-Host ('  占用者进程号 PID：' + $ownerPid)
    Write-Host ('  进程名：' + $procName)
    Write-Host '  很可能是上一次启动的 AGH 还开着（找到那个窗口按 Ctrl+C 或关闭它也可以）。'
    Write-Host '下一步（确认这个进程可以结束后，自己复制运行；本脚本不会替你结束它）：' -ForegroundColor Yellow
    Write-Host ('  Stop-Process -Id ' + $ownerPid)
    Write-Host '然后重新运行：'
    Write-Host ('  ' + $RunCommand)
    Write-Host ('或者改用别的端口：' + $RunCommand + ' -Port ' + ($Port + 1))
    exit 1
}
Write-Host '  端口空闲。'

# ---- 4. 启动（前台运行，不重定向） ----
Write-Host ''
Write-Host '[4/4] 启动 AGH' -ForegroundColor Cyan
Write-Host ('  启动后请用浏览器打开：http://127.0.0.1:' + $Port + '/') -ForegroundColor Green
Write-Host '  按 Ctrl+C 或关闭此窗口即可停止'
Write-Host '  第一次启动需要几秒钟，下面出现网址就表示成功了。'
Write-Host ''

& $Node $Runtime serve --port $Port
$code = $LASTEXITCODE

Write-Host ''
if ($code -eq 0) {
    Write-Host 'AGH 已停止。想再启动，运行：' -ForegroundColor Cyan
} else {
    Write-Host ('AGH 已退出，退出码 ' + $code + '（正常停止是 0 或 130）。上面是具体原因。') -ForegroundColor Yellow
    Write-Host ('如果还没安装过插件，先运行：' + $InstallCommand)
    Write-Host '如果网页能打开，但插件提示找不到项目内核：AGH 的后台进程可能还沿用着旧的环境变量。先停掉它再重新启动：'
    Write-Host ('  & "' + $Node + '" "' + $Runtime + '" daemon stop --profile ' + $AghProfile)
    Write-Host '再启动，运行：'
}
Write-Host ('  ' + $RunCommand)
exit $code
