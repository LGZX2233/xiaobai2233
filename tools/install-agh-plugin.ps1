<#
  install-agh-plugin.ps1  把 Project Kernel 插件装进 AGH（Windows PowerShell 5.1）

  作用：自动完成「卸载旧版 -> 安装 -> 信任 -> 启用」。中间 AGH 会问一次
        "Install ...? [y/N]"，这一步必须你亲自输入 y 再按回车。

  运行方式（Windows 默认禁止直接运行 .ps1，请在仓库目录里粘贴下面这一行）：
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\install-agh-plugin.ps1

  装完以后启动 AGH：
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\start-agh.ps1

  说明：脚本会切换到仓库根目录（tools 文件夹的上一级），因为安装源
        file:./adapters/agh-plugin 是相对这个目录解析的。
  信任步骤用到的 integrity 和 capabilityHash 取自 AGH 自己写下的安装记录
  （operations.json），不是手写的，也不会使用旧记录。
#>
param(
    [string]$Runtime = 'D:\bisai\agh-build\runtime\agnes.mjs',
    [string]$AghHome = 'D:\bisai\kernel-agh-work\agh-native-17e504be-56d6-4f89-aaa3-b69eda1b3a3c',
    [string]$Node = 'node'
)

$ErrorActionPreference = 'Continue'

$PackageId = '@project-kernel/agh-plugin'
$PackageSource = 'file:./adapters/agh-plugin'
$AghProfile = 'local-dev'

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
$RepoRoot = Split-Path -Parent $ScriptDir

$RunCommand = 'powershell -NoProfile -ExecutionPolicy Bypass -File tools\install-agh-plugin.ps1'
$StartCommand = 'powershell -NoProfile -ExecutionPolicy Bypass -File tools\start-agh.ps1'

# ======================================================================
# 函数（Get-NewestPluginRecord 等可以单独拿出来测试）
# ======================================================================

# 把时间统一成 "yyyy-MM-ddTHH:mm:ss.fffZ"（UTC）字符串，便于按字符串比较先后。
# Windows PowerShell 5.1 的 ConvertFrom-Json 返回字符串；PowerShell 7 会返回 DateTime，这里两种都处理。
function ConvertTo-IsoUtc {
    param($Value)
    if ($null -eq $Value) { return '' }
    $format = "yyyy-MM-dd'T'HH:mm:ss.fff'Z'"
    $culture = [System.Globalization.CultureInfo]::InvariantCulture
    if ($Value -is [datetime]) {
        return $Value.ToUniversalTime().ToString($format, $culture)
    }
    $text = [string]$Value
    if (-not $text) { return '' }
    $parsed = [datetime]::MinValue
    $styles = [System.Globalization.DateTimeStyles]'AdjustToUniversal,AssumeUniversal'
    if ([datetime]::TryParse($text, $culture, $styles, [ref]$parsed)) {
        return $parsed.ToString($format, $culture)
    }
    return $text
}

# 读取 operations.json，返回记录列表。每条记录有：
#   Operation, State, StartedAt, PackageId, Integrity, CapabilityHash, Version
# 先用 ConvertFrom-Json；失败（文件被截断、过大等）时退回正则逐条提取。
function Read-OperationRecords {
    param([string]$Path)
    $records = New-Object System.Collections.ArrayList
    if (-not $Path) { return @() }
    if (-not (Test-Path -LiteralPath $Path)) { return @() }
    $raw = $null
    try { $raw = Get-Content -Raw -Encoding UTF8 -LiteralPath $Path -ErrorAction Stop } catch { $raw = $null }
    if (-not $raw) { return @() }

    $parsed = $null
    try { $parsed = $raw | ConvertFrom-Json -ErrorAction Stop } catch { $parsed = $null }

    if ($null -ne $parsed -and $null -ne $parsed.operations) {
        foreach ($entry in @($parsed.operations)) {
            $op = $entry.operation
            if ($null -eq $op) { continue }
            $pkg = ''
            if ($op.packageId) { $pkg = [string]$op.packageId }
            elseif ($op.preview -and $op.preview.id) { $pkg = [string]$op.preview.id }
            elseif ($op.installed -and $op.installed.id) { $pkg = [string]$op.installed.id }
            $integrity = ''
            $capability = ''
            $version = ''
            foreach ($source in @($op.installed, $op.preview)) {
                if ($null -eq $source) { continue }
                if ($integrity) { continue }
                if ($source.integrity -and $source.capabilityHash) {
                    $integrity = [string]$source.integrity
                    $capability = [string]$source.capabilityHash
                    $version = [string]$source.version
                }
            }
            $item = New-Object PSObject -Property @{
                Operation      = [string]$op.operation
                State          = [string]$op.state
                StartedAt      = (ConvertTo-IsoUtc $op.startedAt)
                PackageId      = $pkg
                Integrity      = $integrity
                CapabilityHash = $capability
                Version        = $version
            }
            [void]$records.Add($item)
        }
        return $records
    }

    # ---- 正则退路：按 {"operation":{"operationId" 切成一条条记录 ----
    $chunks = [regex]::Split($raw, '(?=\{\s*"operation"\s*:\s*\{\s*"operationId")')
    foreach ($chunk in $chunks) {
        if ($chunk -notmatch '^\{\s*"operation"\s*:\s*\{\s*"operationId"') { continue }
        $opName = ''
        $state = ''
        $started = ''
        $pkg = ''
        $integrity = ''
        $capability = ''
        $version = ''
        $m = [regex]::Match($chunk, '"operation"\s*:\s*"([a-z]+)"')
        if ($m.Success) { $opName = $m.Groups[1].Value }
        $m = [regex]::Match($chunk, '"state"\s*:\s*"([a-z]+)"')
        if ($m.Success) { $state = $m.Groups[1].Value }
        $m = [regex]::Match($chunk, '"startedAt"\s*:\s*"([^"]+)"')
        if ($m.Success) { $started = ConvertTo-IsoUtc $m.Groups[1].Value }
        $m = [regex]::Match($chunk, '"packageId"\s*:\s*"([^"]+)"')
        if ($m.Success) { $pkg = $m.Groups[1].Value }
        else {
            $m = [regex]::Match($chunk, '"id"\s*:\s*"([^"]+)"')
            if ($m.Success) { $pkg = $m.Groups[1].Value }
        }
        $m = [regex]::Match($chunk, '"integrity"\s*:\s*"(sha256-[^"]+)"')
        if ($m.Success) { $integrity = $m.Groups[1].Value }
        $m = [regex]::Match($chunk, '"capabilityHash"\s*:\s*"([0-9a-f]{64})"')
        if ($m.Success) { $capability = $m.Groups[1].Value }
        $m = [regex]::Match($chunk, '"version"\s*:\s*"([^"]+)"')
        if ($m.Success) { $version = $m.Groups[1].Value }
        if (-not $integrity -or -not $capability) { $integrity = ''; $capability = ''; $version = '' }
        $item = New-Object PSObject -Property @{
            Operation      = $opName
            State          = $state
            StartedAt      = $started
            PackageId      = $pkg
            Integrity      = $integrity
            CapabilityHash = $capability
            Version        = $version
        }
        [void]$records.Add($item)
    }
    return $records
}

# 所有记录里最新的开始时间（ISO UTC 字符串）；没有记录返回空字符串。
function Get-LatestOperationTime {
    param([string]$Path)
    $latest = ''
    foreach ($r in @(Read-OperationRecords -Path $Path)) {
        if ($r.StartedAt -and [string]::CompareOrdinal($r.StartedAt, $latest) -gt 0) { $latest = $r.StartedAt }
    }
    return $latest
}

# 找出「这一次安装」留下的最新记录。条件（全部满足）：
#   state 为 completed；包名等于 -PackageId；操作类型在 -Operation 里（默认 inspect 和 install）；
#   同时有 integrity（sha256-...）和 capabilityHash（64 位十六进制）；
#   开始时间严格晚于 -After（-After 为空表示不限制）。
# 返回对象有 Integrity / CapabilityHash / Version / StartedAt（另有 Operation, PackageId, State）；找不到返回 $null。
function Get-NewestPluginRecord {
    param(
        [string]$Path,
        [string]$PackageId,
        $After = '',
        [string[]]$Operation = @('inspect', 'install')
    )
    $afterText = ConvertTo-IsoUtc $After
    $best = $null
    foreach ($r in @(Read-OperationRecords -Path $Path)) {
        if ($r.State -ne 'completed') { continue }
        if ($r.PackageId -ne $PackageId) { continue }
        if ($Operation -notcontains $r.Operation) { continue }
        if ($r.Integrity -notmatch '^sha256-[A-Za-z0-9+/=_-]+$') { continue }
        if ($r.CapabilityHash -notmatch '^[0-9a-f]{64}$') { continue }
        if ($afterText -and ([string]::CompareOrdinal($r.StartedAt, $afterText) -le 0)) { continue }
        if ($null -eq $best -or [string]::CompareOrdinal($r.StartedAt, $best.StartedAt) -ge 0) { $best = $r }
    }
    return $best
}

# 运行 "package <参数>" 并收集输出（只用于 status 这类非交互命令）。
function Invoke-AghCaptured {
    param([string[]]$AghArguments)
    $allArgs = @($Runtime, 'package', '--profile', $AghProfile) + $AghArguments
    $lines = @(& $Node @allArgs 2>&1 | ForEach-Object { [string]$_ })
    $code = $LASTEXITCODE
    return New-Object PSObject -Property @{ ExitCode = $code; Lines = $lines }
}

# AGH status 的真实输出格式（packages/cli/src/commands/package.ts）：
#   <id>@<version> desired=<..> actual=<..> trusted=<true|false>
# 没有任何包时输出 "No packages installed."
function Get-PluginStatusLine {
    param([string[]]$Lines, [string]$Id)
    $pattern = '^\s*' + [regex]::Escape($Id) + '@\S+\s'
    foreach ($line in $Lines) {
        if ($line -match $pattern) { return $line.Trim() }
    }
    return $null
}

function Stop-WithError {
    param([string[]]$Lines)
    Write-Host ''
    foreach ($line in $Lines) { Write-Host $line -ForegroundColor Red }
    exit 1
}

# ======================================================================
# 主流程
# ======================================================================

Write-Host ''
Write-Host '安装 Project Kernel 插件到 AGH' -ForegroundColor Cyan
Write-Host ('脚本会先切换到仓库目录：' + $RepoRoot)
Write-Host '（安装源 file:./adapters/agh-plugin 是相对这个目录的）'

# ---- 0. 检查 ----
Write-Host ''
Write-Host '[0/5] 检查环境' -ForegroundColor Cyan
Set-Location -LiteralPath $RepoRoot

$pluginManifest = Join-Path $RepoRoot 'adapters\agh-plugin\package.json'
if (-not (Test-Path -LiteralPath $pluginManifest)) {
    Stop-WithError @(
        '未完成：找不到插件目录 adapters\agh-plugin\package.json。',
        ('  期望位置：' + $pluginManifest),
        '请确认本脚本放在 kernel_next 仓库的 tools 文件夹里，并按下面的方式运行：',
        ('  ' + $RunCommand)
    )
}
if (-not (Test-Path -LiteralPath $Runtime)) {
    Stop-WithError @(
        '未完成：找不到 AGH 运行文件 agnes.mjs。',
        ('  期望位置：' + $Runtime),
        '下一步：如果它在别的位置，请指定完整路径重试：',
        ('  ' + $RunCommand + ' -Runtime "agnes.mjs 的完整路径"')
    )
}
if (-not (Get-Command $Node -ErrorAction SilentlyContinue)) {
    Stop-WithError @(
        ('未完成：找不到 Node.js（命令 ' + $Node + '）。AGH 需要 Node.js 24 或更新版本。'),
        '下一步：安装 Node.js 24 后重新打开 PowerShell；如果你已经有 node.exe，指定它的完整路径：',
        ('  ' + $RunCommand + ' -Node "C:\...\node.exe"')
    )
}
$nodeVersion = ''
try { $nodeVersion = [string](& $Node --version 2>&1 | Select-Object -First 1) } catch { $nodeVersion = '' }
if (-not $nodeVersion -or $nodeVersion -notmatch '^v?\d+\.') {
    Stop-WithError @(
        ('未完成：运行「' + $Node + ' --version」没有得到版本号，这个 Node 不能用。'),
        '下一步：安装 Node.js 24，或用 -Node 指定正确的 node.exe 完整路径。'
    )
}
Write-Host ('  Node 版本：' + $nodeVersion)
if ($nodeVersion -match '^v?(\d+)\.' -and [int]$Matches[1] -lt 24) {
    Write-Host '  提醒：AGH 要求 Node.js 24 或更新，当前版本偏旧，失败时请先升级 Node。' -ForegroundColor Yellow
}

# AGH 的后台进程第一次启动时会继承这些环境变量，所以这里和 start-agh.ps1 保持一致。
$env:AGH_HOME = $AghHome
$env:AGNES_PROFILE = $AghProfile
$env:PK_KERNEL_ROOT = $RepoRoot
$venvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venvPython) {
    $env:PK_PYTHON = $venvPython
} else {
    Write-Host '  提醒：还没有 .venv\Scripts\python.exe，安装可以继续，但启动 AGH 前需要先建好 Python 环境：' -ForegroundColor Yellow
    Write-Host ('    cd "' + $RepoRoot + '"; py -3.12 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e .') -ForegroundColor Yellow
}
Write-Host ('  AGH_HOME      = ' + $env:AGH_HOME)
Write-Host ('  AGNES_PROFILE = ' + $env:AGNES_PROFILE)

$operationsFile = Join-Path $AghHome 'data\daemon\package-operations\operations.json'

# ---- (a) 清理旧版本 ----
Write-Host ''
Write-Host '[1/5] 检查是否已经装过旧版本' -ForegroundColor Cyan
$status = Invoke-AghCaptured -AghArguments @('status')
if ($status.ExitCode -ne 0) {
    Write-Host ($status.Lines -join "`n")
    Stop-WithError @(
        ('未完成：读取 AGH 插件列表失败（退出码 ' + $status.ExitCode + '），原因见上面的输出。'),
        '常见原因：Node 版本太旧，或 AGH_HOME 路径不对。',
        '下一步：解决后重新运行：',
        ('  ' + $RunCommand)
    )
}
$existing = Get-PluginStatusLine -Lines $status.Lines -Id $PackageId
if ($existing) {
    Write-Host ('  发现旧版本：' + $existing)
    Write-Host '  先停用再移除旧版本……'
    & $Node $Runtime package --profile $AghProfile disable $PackageId
    if ($LASTEXITCODE -ne 0) { Write-Host '  （停用没有成功，可能本来就没启用，继续尝试移除）' -ForegroundColor Yellow }
    & $Node $Runtime package --profile $AghProfile remove $PackageId
    if ($LASTEXITCODE -ne 0) { Write-Host '  （移除没有成功，下面会再确认一次）' -ForegroundColor Yellow }
    $status = Invoke-AghCaptured -AghArguments @('status')
    $still = Get-PluginStatusLine -Lines $status.Lines -Id $PackageId
    if ($still) {
        Stop-WithError @(
            '未完成：旧版本没能移除，仍然在列表里：',
            ('  ' + $still),
            '下一步：看上面 disable / remove 的报错信息，处理后重新运行：',
            ('  ' + $RunCommand)
        )
    }
    Write-Host '  旧版本已移除。'
} else {
    Write-Host '  没有旧版本，直接安装。'
}

# ---- (b) 安装（必须在真实控制台里运行，不能重定向，否则 AGH 不会提问） ----
$marker = Get-LatestOperationTime -Path $operationsFile
if ($marker) { Write-Host ('  安装前的最新记录时间标记：' + $marker) }

Write-Host ''
Write-Host '[2/5] 安装插件' -ForegroundColor Cyan
Write-Host '接下来 AGH 会问 Install ...? [y/N]，请输入 y 再按回车' -ForegroundColor Yellow
Write-Host '（输入 n、直接回车、或按 Ctrl+C 都会取消安装；取消后重新运行本脚本即可）'
Write-Host ''

& $Node $Runtime package --profile $AghProfile add $PackageSource
$addExit = $LASTEXITCODE

Write-Host ''
if ($addExit -ne 0) {
    Write-Host ('安装命令返回了错误（退出码 ' + $addExit + '），原因见上面的输出。') -ForegroundColor Yellow
}

# ---- (c) 从 AGH 的操作记录里取出这一次的 integrity 和 capabilityHash ----
Write-Host '[3/5] 读取 AGH 记录的安装信息' -ForegroundColor Cyan
$record = $null
for ($attempt = 1; $attempt -le 6; $attempt++) {
    $record = Get-NewestPluginRecord -Path $operationsFile -PackageId $PackageId -After $marker -Operation @('install')
    if ($null -ne $record) { break }
    Start-Sleep -Seconds 1
}
if ($null -eq $record) {
    $previewOnly = Get-NewestPluginRecord -Path $operationsFile -PackageId $PackageId -After $marker -Operation @('inspect')
    if ($null -ne $previewOnly) {
        Stop-WithError @(
            '没有安装：AGH 只显示了预览，没有执行安装。',
            '最可能的原因：提示 Install ...? [y/N] 时输入的不是 y（或者直接按了回车）。',
            '为了安全，脚本不会拿旧记录去信任插件，已停止。',
            '下一步：重新运行，到提示时输入 y 再按回车：',
            ('  ' + $RunCommand)
        )
    }
    Stop-WithError @(
        '没有安装：在 AGH 的操作记录里找不到这一次安装的记录。',
        ('  记录文件：' + $operationsFile),
        '可能原因：安装命令报错了（看上面的输出），或 AGH_HOME 路径不对。',
        '为了安全，脚本不会拿旧记录去信任插件，已停止。',
        '下一步：处理上面的报错后重新运行：',
        ('  ' + $RunCommand)
    )
}
Write-Host ('  版本：' + $record.Version)
Write-Host ('  integrity：' + $record.Integrity)
Write-Host ('  capabilityHash：' + $record.CapabilityHash)
Write-Host ('  记录时间：' + $record.StartedAt)

# ---- (d) 信任、启用、核对 ----
Write-Host ''
Write-Host '[4/5] 信任并启用插件' -ForegroundColor Cyan
& $Node $Runtime package --profile $AghProfile trust $PackageId $record.Integrity $record.CapabilityHash
$trustExit = $LASTEXITCODE
if ($trustExit -ne 0) {
    Stop-WithError @(
        ('未完成：信任步骤失败（退出码 ' + $trustExit + '），原因见上面的输出。'),
        '下一步：重新运行本脚本（它会先清理再重装）：',
        ('  ' + $RunCommand)
    )
}
& $Node $Runtime package --profile $AghProfile enable $PackageId
$enableExit = $LASTEXITCODE
if ($enableExit -ne 0) {
    Stop-WithError @(
        ('未完成：启用步骤失败（退出码 ' + $enableExit + '），原因见上面的输出。'),
        '下一步：重新运行本脚本（它会先清理再重装）：',
        ('  ' + $RunCommand)
    )
}

Write-Host ''
Write-Host '[5/5] 核对最终状态' -ForegroundColor Cyan
$finalLine = $null
$ok = $false
for ($attempt = 1; $attempt -le 6; $attempt++) {
    $status = Invoke-AghCaptured -AghArguments @('status')
    $finalLine = Get-PluginStatusLine -Lines $status.Lines -Id $PackageId
    if ($finalLine -and $finalLine -match 'actual=running' -and $finalLine -match 'trusted=true') { $ok = $true; break }
    Start-Sleep -Seconds 2
}
if ($finalLine) { Write-Host ('  ' + $finalLine) } else { Write-Host ($status.Lines -join "`n") }

Write-Host ''
if ($ok) {
    Write-Host '完成：插件已安装、已信任、正在运行。' -ForegroundColor Green
    Write-Host '下一步：启动 AGH（复制下面这一行回车）：'
    Write-Host ('  ' + $StartCommand)
    exit 0
}
Write-Host '安装步骤都执行了，但状态还不是「运行中且已信任」（需要 actual=running 和 trusted=true）。' -ForegroundColor Red
Write-Host '下一步：重新运行本脚本（它会先清理旧版本再重装）：'
Write-Host ('  ' + $RunCommand)
exit 1
