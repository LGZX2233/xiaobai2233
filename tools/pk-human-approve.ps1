<#
  pk-human-approve.ps1  人工审批入口（Windows PowerShell 5.1）

  作用：打开 Project Kernel 的人工审批界面。你要亲自核对「快照摘要」，
        输入摘要前 8 位表示批准，输入 r 表示拒绝，直接回车表示取消。

  运行方式（Windows 默认禁止直接运行 .ps1，请在仓库目录里粘贴下面这一行）：
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\pk-human-approve.ps1

  如果脚本找不到运行目录，可以手动指定（目录名以 pk-agh-demo- 开头，里面有 demo.sqlite）：
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\pk-human-approve.ps1 -Root "C:\Users\你的用户名\AppData\Local\Temp\pk-agh-demo-xxxx"

  注意：这一步必须在真正的 PowerShell 窗口里亲自操作。不要重定向或管道输出，
        否则 Python 检测不到终端，会拒绝执行（这是有意的设计）。
#>
param([string]$Root)

$ErrorActionPreference = 'Continue'

# 仓库根目录 = tools 文件夹的上一级
$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
$RepoRoot = Split-Path -Parent $ScriptDir

$RunCommand = 'powershell -NoProfile -ExecutionPolicy Bypass -File tools\pk-human-approve.ps1'
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$ApproveScript = Join-Path $RepoRoot 'tools\pk_human_approve.py'
$PointerName = 'pk-agh-last-root.txt'

# 与 Node 的 os.tmpdir() 在 Windows 上的顺序一致：TEMP，然后 TMP，最后 SystemRoot\temp
function Get-NodeTempDir {
    if ($env:TEMP) { return $env:TEMP }
    if ($env:TMP) { return $env:TMP }
    $sysRoot = $env:SystemRoot
    if (-not $sysRoot) { $sysRoot = $env:windir }
    if ($sysRoot) { return ($sysRoot + '\temp') }
    return $null
}

function Stop-WithError {
    param([string[]]$Lines)
    Write-Host ''
    foreach ($line in $Lines) { Write-Host $line -ForegroundColor Red }
    exit 1
}

# ---- 1. 检查 Python 虚拟环境 ----
if (-not (Test-Path -LiteralPath $Python)) {
    $fix = 'cd "' + $RepoRoot + '"; py -3.12 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e .'
    Stop-WithError @(
        '未完成：找不到项目的 Python 环境。',
        ('  缺少文件：' + $Python),
        '下一步：复制下面这一整行，粘贴到 PowerShell 里回车（需要已安装 Python 3.12，安装过程要联网，等它跑完）：',
        ('  ' + $fix),
        '然后再运行本脚本：',
        ('  ' + $RunCommand)
    )
}
if (-not (Test-Path -LiteralPath $ApproveScript)) {
    Stop-WithError @(
        '未完成：找不到审批程序 tools\pk_human_approve.py。',
        ('  期望位置：' + $ApproveScript),
        '请确认你是在 kernel_next 仓库里运行本脚本。'
    )
}

# ---- 2. 确定运行目录 ----
if (-not $Root) {
    $tempDir = Get-NodeTempDir
    if (-not $tempDir) {
        Stop-WithError @(
            '未完成：找不到临时目录（环境变量 TEMP / TMP 都没有设置），无法读取运行目录指针。',
            '下一步：手动指定运行目录后重试：',
            ('  ' + $RunCommand + ' -Root "运行目录的完整路径"')
        )
    }
    $pointer = Join-Path $tempDir $PointerName
    if (-not (Test-Path -LiteralPath $pointer)) {
        Stop-WithError @(
            '未完成：还没有找到 AGH 的运行记录。',
            ('  找过的文件：' + $pointer),
            '可能原因：AGH 还没有调用过任何 pk_ 工具。',
            '下一步：先回到 AGH 网页，让智能体调用一次 Project Kernel 的工具，再重新运行：',
            ('  ' + $RunCommand),
            '或者你已经知道运行目录，就手动指定：',
            ('  ' + $RunCommand + ' -Root "运行目录的完整路径"')
        )
    }
    $Root = ''
    try { $Root = (Get-Content -Raw -Encoding UTF8 -LiteralPath $pointer -ErrorAction Stop).Trim() } catch { $Root = '' }
    if (-not $Root) {
        Stop-WithError @(
            '未完成：运行目录指针文件是空的。',
            ('  文件：' + $pointer),
            '下一步：回到 AGH，让智能体再调用一次 pk_ 工具，然后重新运行：',
            ('  ' + $RunCommand)
        )
    }
}

$Database = Join-Path $Root 'demo.sqlite'
if (-not (Test-Path -LiteralPath $Database)) {
    Stop-WithError @(
        '未完成：这个目录里没有 demo.sqlite，不是插件的运行目录。',
        ('  运行目录：' + $Root),
        '可能原因：AGH 还没有调用过任何 pk_ 工具，或者目录已被清理。',
        '下一步：回到 AGH，让智能体调用一次 pk_ 工具，然后重新运行：',
        ('  ' + $RunCommand),
        '也可以手动指定运行目录：',
        ('  ' + $RunCommand + ' -Root "运行目录的完整路径"')
    )
}

# ---- 3. 告诉用户要做什么，然后交给 Python（交互式，不重定向、不管道） ----
Write-Host ''
Write-Host '人工审批：核对快照摘要后输入前 8 位批准，输入 r 拒绝' -ForegroundColor Cyan
Write-Host '  - 屏幕上会列出待审批的交付请求和「快照摘要」。'
Write-Host '  - 确认无误：输入摘要的前 8 位字符，回车 = 批准。'
Write-Host '  - 不同意：输入 r，回车 = 拒绝（会要求写理由）。'
Write-Host '  - 想放弃：什么都不输入，直接回车 = 取消，不做任何决定。'
Write-Host ('  运行目录：' + $Root)
Write-Host ''

& $Python -I -X utf8 $ApproveScript --root $Root
$code = $LASTEXITCODE

if ($code -ne 0) {
    Write-Host ''
    Write-Host ('审批程序已结束，退出码 ' + $code + '（0 才表示正常完成；上面是具体原因）。') -ForegroundColor Yellow
    Write-Host ('需要重来的话，再运行：' + $RunCommand)
}
exit $code
