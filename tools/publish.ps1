<#
.SYNOPSIS
  Project Kernel 发布助手：把整理好的文件夹安全地推送到 GitHub 仓库。

.DESCRIPTION
  一共 6 步：
    1. 检查电脑上有没有 Git
    2. 检查要发布的文件夹
    3. 从 GitHub 下载仓库现有内容（临时副本）
    4. 把你的文件复制进副本（只新增或替换，绝不删除）
    5. 显示改动清单，等你确认
    6. 提交并正常推送（从不使用强制推送）

  用法（在 PowerShell 里粘贴这一行，把路径换成你解压后的位置）：
    powershell -NoProfile -ExecutionPolicy Bypass -File "<解压后的文件夹>\xiaobai2233\tools\publish.ps1"

.PARAMETER TreeDir
  要发布的文件夹。默认是本脚本所在文件夹的上一级。

.PARAMETER RepoUrl
  目标仓库地址，默认 https://github.com/LGZX2233/xiaobai2233.git

.PARAMETER Branch
  目标分支，默认 main。

.PARAMETER WorkDir
  临时工作文件夹，默认放在系统临时目录里（用完可以放心删除）。

.PARAMETER CommitMessage
  提交说明。

.PARAMETER DryRun
  演练模式：不会真正推送。

.PARAMETER Yes
  跳过确认提问（给自动化测试用，平时不需要）。
#>
[CmdletBinding()]
param(
    [string]$TreeDir = '',
    [string]$RepoUrl = 'https://github.com/LGZX2233/xiaobai2233.git',
    [string]$Branch = 'main',
    [string]$WorkDir = '',
    [string]$CommitMessage = 'Project Kernel: AGH plugin, kernel, panel and docs',
    [switch]$DryRun,
    [switch]$Yes
)

$ErrorActionPreference = 'Stop'
$script:TotalSteps = 6
$script:Repo = ''          # 临时副本里的仓库文件夹
$script:WorkDirFull = ''   # 临时工作文件夹
$script:TreeFull = ''      # 要发布的文件夹（完整路径）
$script:TreeTrim = ''      # 同上，去掉末尾的反斜杠（robocopy 需要）
$script:HeadBefore = ''    # 下载下来时的最新提交

$script:ScriptDir = $PSScriptRoot
if ([string]::IsNullOrEmpty($script:ScriptDir)) {
    if ($MyInvocation.MyCommand.Path) { $script:ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
    else { $script:ScriptDir = (Get-Location).Path }
}

# ---------- 通用小工具 ----------

function Write-Step {
    param([int]$Number, [string]$Text)
    Write-Host ''
    Write-Host ('第 {0} 步 / 共 {1} 步：{2}' -f $Number, $script:TotalSteps, $Text) -ForegroundColor Cyan
}
function Write-Ok { param([string]$Text) Write-Host ('  [OK] ' + $Text) -ForegroundColor Green }
function Write-Note { param([string]$Text) Write-Host ('  ' + $Text) }
function Write-Warn { param([string]$Text) Write-Host ('  [注意] ' + $Text) -ForegroundColor Yellow }

# 出错时：用简单的话说明原因和下一步，然后退出（退出码 1）
function Fail {
    param(
        [string]$Message,
        [string[]]$Hints = @(),
        [string[]]$Output = @(),
        [string]$Reassure = '没有任何东西被推送，你自己的文件夹也没有被改动。'
    )
    Write-Host ''
    Write-Host ('出问题了：' + $Message) -ForegroundColor Red
    foreach ($h in $Hints) { Write-Host ('  ' + $h) -ForegroundColor Yellow }
    if ($Output.Count -gt 0) {
        Write-Host '  程序给出的原始信息（需要时请整段复制发给开发者）：' -ForegroundColor DarkGray
        foreach ($l in ($Output | Select-Object -Last 15)) { Write-Host ('    ' + $l) -ForegroundColor DarkGray }
    }
    if ($Reassure) { Write-Host ''; Write-Host $Reassure -ForegroundColor Green }
    if ($script:WorkDirFull) {
        Write-Host ('临时文件夹（里面只是副本，可以放心删除）：' + $script:WorkDirFull) -ForegroundColor DarkGray
    }
    exit 1
}

# 运行外部程序：临时把 ErrorActionPreference 设为 Continue，
# 这样 git 往 stderr 写进度信息时，PowerShell 5.1 不会当成错误中断。
# 返回对象：ExitCode（退出码）、Lines（输出的每一行）。
function Invoke-Native {
    param([string]$Exe, [string[]]$ArgList = @(), [switch]$DropStderr)
    $oldPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $code = 0
    $lines = @()
    try {
        if ($DropStderr) { $raw = @(& $Exe @ArgList 2>$null) }
        else { $raw = @(& $Exe @ArgList 2>&1) }
        $code = $LASTEXITCODE
        $lines = @($raw | ForEach-Object { [string]$_ })
    }
    finally {
        $ErrorActionPreference = $oldPref
    }
    return New-Object psobject -Property @{ ExitCode = $code; Lines = $lines }
}

# 运行 git。-c core.quotepath=false 让中文文件名按原样显示（不显示成 \346\226... 这种转义）。
function Invoke-Git {
    param(
        [string[]]$GitArgs,
        [string]$Dir = '',
        [string[]]$ExtraConfig = @(),
        [switch]$DropStderr
    )
    $all = @('-c', 'core.quotepath=false')
    foreach ($c in $ExtraConfig) { $all += @('-c', $c) }
    if ($Dir -ne '') { $all += @('-C', $Dir) }
    $all += $GitArgs
    return (Invoke-Native -Exe 'git' -ArgList $all -DropStderr:$DropStderr)
}

# 取 git 输出的第一行（失败则返回空字符串）
function Get-GitLine {
    param([string]$Dir, [string[]]$GitArgs)
    $r = Invoke-Git -Dir $Dir -GitArgs $GitArgs -DropStderr
    if ($r.ExitCode -ne 0) { return '' }
    $first = $r.Lines | Where-Object { $_ -ne '' } | Select-Object -First 1
    if ($null -eq $first) { return '' }
    return ([string]$first).Trim()
}

# 根据 git 的报错文字，给出通俗的原因和办法
function Get-GitHints {
    param([string]$Text, [string]$Phase)
    $t = $Text.ToLowerInvariant()
    if ($t -match 'authentication failed|could not read username|could not read password|permission denied|denied to|invalid username or password|returned error: 40[13]|password authentication was removed|terminal prompts disabled|bad credentials') {
        return @(
            '原因：登录没有成功（GitHub 不认识这次登录，或者这个账号没有权限）。',
            '办法：重新运行本脚本。弹出登录窗口时，请用拥有 LGZX2233/xiaobai2233 仓库权限的 GitHub 账号登录。',
            '如果窗口要你输入密码：GitHub 不再接受账号密码，请到 GitHub 网站的 Settings > Developer settings > Personal access tokens 生成一个令牌（token），把令牌当作密码粘贴进去。'
        )
    }
    if ($Phase -eq 'push' -and $t -match 'non-fast-forward|fetch first|\[rejected\]|\[remote rejected\]|stale info|updates were rejected|failed to push some refs') {
        return @(
            '原因：GitHub 拒绝了这次推送。通常是因为 GitHub 上的内容在你下载之后又有了新改动，或者这个分支受保护。',
            '这个脚本不会强行覆盖任何东西，所以 GitHub 上的原有内容完好无损。',
            '办法：先不要重复尝试，请把上面的原始信息整段复制发给开发者。'
        )
    }
    if ($Phase -eq 'clone' -and $t -match 'remote branch .* not found|repository not found|does not exist|not found') {
        return @(
            '原因：找不到这个仓库或这个分支（地址写错了，或者仓库是私有的而你还没登录）。',
            '办法：请把上面的原始信息整段复制发给开发者。'
        )
    }
    if ($t -match 'could not resolve host|failed to connect|connection (timed out|refused|reset)|timed out|network is unreachable|ssl|schannel|unable to access|early eof|rpc failed|unexpected disconnect|could not connect') {
        return @(
            '原因：电脑连不上 GitHub（网络问题）。',
            '办法：检查网络是否正常，能不能在浏览器里打开 https://github.com 。如果平时需要代理或 VPN，请先打开它，再重新运行本脚本。重新运行不会有任何副作用。'
        )
    }
    return @(
        '原因：暂时没能判断出具体原因。',
        '办法：请把上面的原始信息整段复制发给开发者。'
    )
}

# =====================================================================
#  开始
# =====================================================================
Write-Host ''
Write-Host 'Project Kernel 发布助手' -ForegroundColor Cyan
Write-Host '它会把你整理好的文件推送到 GitHub。一共 6 步，每一步都会告诉你发生了什么。'
Write-Host '放心：它只会新增或替换文件，不会删除 GitHub 上已有的东西，也不会强制覆盖。'
if ($DryRun) {
    Write-Host '【演练模式】这一次不会真正推送，只是完整地走一遍流程。' -ForegroundColor Yellow
}

# 让中文在窗口里正常显示（失败也没关系）
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

# =====================================================================
#  第 1 步：检查 Git
# =====================================================================
Write-Step 1 '检查电脑上有没有 Git（一个免费的文件版本管理工具）'
$gitCmd = Get-Command git -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $gitCmd) {
    Fail '这台电脑上没有找到 Git。' -Hints @(
        '办法：',
        '  1) 用浏览器打开 https://git-scm.com/download/win ，下载并安装 Git for Windows（一路点「下一步」即可）。',
        '  2) 安装完成后，关闭当前窗口，重新打开 PowerShell，再运行一次同样的命令。'
    ) -Reassure '什么都还没有发生，不会有任何改动。'
}
$gitVer = Get-GitLine -Dir '' -GitArgs @('--version')
if ($gitVer -eq '') { $gitVer = 'git' }
Write-Ok ('已找到 Git：' + $gitVer)

# =====================================================================
#  第 2 步：检查要发布的文件夹
# =====================================================================
Write-Step 2 '检查要发布的文件夹'

function Test-IsTree {
    param([string]$Dir)
    if (-not (Test-Path -LiteralPath $Dir -PathType Container)) { return $false }
    if (-not (Test-Path -LiteralPath (Join-Path $Dir 'pyproject.toml') -PathType Leaf)) { return $false }
    $srcPk = Join-Path (Join-Path $Dir 'src') 'project_kernel'
    return (Test-Path -LiteralPath $srcPk -PathType Container)
}

if ([string]::IsNullOrWhiteSpace($TreeDir)) {
    # 默认：脚本在 <文件夹>\tools\publish.ps1，所以文件夹就是脚本所在位置的上一级
    $parentDir = Split-Path -Parent $script:ScriptDir
    $nestedDir = Join-Path $script:ScriptDir 'xiaobai2233'
    if ((-not [string]::IsNullOrEmpty($parentDir)) -and (Test-IsTree $parentDir)) {
        $TreeDir = $parentDir
    }
    elseif (Test-Path -LiteralPath $nestedDir -PathType Container) {
        $TreeDir = $nestedDir
    }
    else {
        Fail '没能自动找到要发布的文件夹。' -Hints @(
            '办法：请确认你是用解压出来的 xiaobai2233\tools\publish.ps1 运行的，不要把脚本单独拷到别处。',
            '也可以手动指定文件夹，例如：',
            '  powershell -NoProfile -ExecutionPolicy Bypass -File "脚本路径" -TreeDir "D:\你的文件夹\xiaobai2233"'
        )
    }
}

try {
    $unresolved = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($TreeDir)
    $script:TreeFull = [System.IO.Path]::GetFullPath($unresolved)
}
catch {
    Fail ('文件夹路径看起来不对：' + $TreeDir) -Hints @('办法：请检查路径里有没有写错的字符，然后重新运行。')
}

# 不允许把整个磁盘根目录当作要发布的文件夹
$rootOfTree = [System.IO.Path]::GetPathRoot($script:TreeFull)
if ($script:TreeFull -eq $rootOfTree) {
    Fail ('这是一个磁盘根目录，不能整盘发布：' + $script:TreeFull) -Hints @('办法：请指定具体的项目文件夹（里面有 README.md 和 pyproject.toml 的那个）。')
}

# 去掉末尾的反斜杠：Windows 里「路径\"」会被当成转义，导致 robocopy 参数错乱
$script:TreeTrim = $script:TreeFull.TrimEnd([char[]]@('\', '/'))
if ($script:TreeTrim -eq '') { $script:TreeTrim = $script:TreeFull }

if (-not (Test-Path -LiteralPath $script:TreeTrim -PathType Container)) {
    Fail ('找不到这个文件夹：' + $script:TreeTrim) -Hints @('办法：请确认已经解压，并且路径没有写错。')
}

$missing = @()
if (-not (Test-Path -LiteralPath (Join-Path $script:TreeTrim 'pyproject.toml') -PathType Leaf)) { $missing += 'pyproject.toml' }
if (-not (Test-Path -LiteralPath (Join-Path (Join-Path $script:TreeTrim 'src') 'project_kernel') -PathType Container)) { $missing += 'src\project_kernel' }
if (-not (Test-Path -LiteralPath (Join-Path $script:TreeTrim 'README.md') -PathType Leaf)) { $missing += 'README.md' }
if ($missing.Count -gt 0) {
    Fail ('这个文件夹看起来不是 Project Kernel 的项目文件夹：' + $script:TreeTrim) -Hints @(
        ('里面缺少：' + ($missing -join '、')),
        '办法：请确认解压完整，并指向里面有 README.md 的那一层文件夹。'
    )
}
Write-Ok ('要发布的文件夹：' + $script:TreeTrim)

# 临时工作文件夹
if ([string]::IsNullOrWhiteSpace($WorkDir)) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $WorkDir = Join-Path ([System.IO.Path]::GetTempPath()) ('xiaobai2233-publish-' + $stamp)
}
try {
    $script:WorkDirFull = [System.IO.Path]::GetFullPath($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($WorkDir))
}
catch {
    Fail ('临时文件夹路径不对：' + $WorkDir)
}
$script:WorkDirFull = $script:WorkDirFull.TrimEnd([char[]]@('\', '/'))

# 临时文件夹不能放在要发布的文件夹里面，否则会把自己复制进去
$sep = [System.IO.Path]::DirectorySeparatorChar
if (($script:WorkDirFull + $sep).StartsWith($script:TreeTrim + $sep, [System.StringComparison]::OrdinalIgnoreCase)) {
    Fail '临时文件夹不能放在要发布的文件夹里面。' -Hints @('办法：不要指定 -WorkDir，使用默认位置即可。')
}

$script:Repo = Join-Path $script:WorkDirFull 'repo'
if (Test-Path -LiteralPath $script:Repo) {
    Fail ('临时文件夹里已经有内容：' + $script:Repo) -Hints @('办法：不要指定 -WorkDir（默认每次都会用新的文件夹），或者换一个新的名字。')
}
try {
    New-Item -ItemType Directory -Path $script:WorkDirFull -Force | Out-Null
}
catch {
    Fail ('无法创建临时文件夹：' + $script:WorkDirFull) -Hints @('办法：请确认磁盘还有空间，并且有权限写入。')
}
Write-Ok ('临时文件夹：' + $script:WorkDirFull + '（只放副本，用完可以放心删除）')

# =====================================================================
#  第 3 步：下载仓库现有内容
# =====================================================================
Write-Step 3 '从 GitHub 下载仓库现有内容（只是下载一份临时副本，不会改动 GitHub）'
Write-Note ('仓库：' + $RepoUrl + '    分支：' + $Branch)
Write-Note '如果仓库需要登录，可能会弹出一个登录窗口，请按提示登录。请稍候……'

$clone = Invoke-Git -GitArgs @('clone', '--branch', $Branch, '--', $RepoUrl, $script:Repo)
if ($clone.ExitCode -ne 0) {
    $hints = Get-GitHints -Text ($clone.Lines -join "`n") -Phase 'clone'
    Fail '没能从 GitHub 下载仓库。' -Hints $hints -Output $clone.Lines
}
Write-Ok '下载完成。'

# 在这份临时副本里（只影响副本）：不转换换行符，让提交里保存的内容和你的文件逐字节一致
foreach ($kv in @(@('core.autocrlf', 'false'), @('core.safecrlf', 'false'), @('core.longpaths', 'true'))) {
    $cfg = Invoke-Git -Dir $script:Repo -GitArgs @('config', '--local', $kv[0], $kv[1])
    if ($cfg.ExitCode -ne 0) {
        Fail ('无法设置临时副本的 Git 选项：' + $kv[0]) -Output $cfg.Lines
    }
}

# 确认下载下来的确有历史记录
$countText = Get-GitLine -Dir $script:Repo -GitArgs @('rev-list', '--count', 'HEAD')
$commitCount = 0
if (-not [int]::TryParse($countText, [ref]$commitCount)) { $commitCount = 0 }
if ($commitCount -lt 1) {
    Fail '下载下来的仓库里没有任何提交记录，看起来是个空仓库。' -Hints @(
        '为了安全，脚本不会往一个空的或异常的仓库里推送。',
        '办法：请把这条信息发给开发者。'
    )
}
$script:HeadBefore = Get-GitLine -Dir $script:Repo -GitArgs @('rev-parse', 'HEAD')
$shortBefore = Get-GitLine -Dir $script:Repo -GitArgs @('rev-parse', '--short', 'HEAD')
Write-Ok ('远程已有 {0} 个提交（最新是 {1}），你的提交会接在后面，不会覆盖。' -f $commitCount, $shortBefore)

# =====================================================================
#  第 4 步：把你的文件复制进临时副本
# =====================================================================
Write-Step 4 '把你的文件复制进临时副本（只新增或替换，绝不删除任何文件）'

# 只用 /E（包含子文件夹）。不使用任何会删除或移动文件的选项，所以不会删除或移动任何东西。
$roboArgs = @(
    $script:TreeTrim, $script:Repo, '/E',
    '/XD', '.git', 'node_modules', '__pycache__', '.venv', '.validation-tmp', '.pytest_cache',
    '/XF', '*.pyc',
    '/NFL', '/NDL', '/NJH', '/NJS', '/NP', '/R:1', '/W:1'
)
$robo = Invoke-Native -Exe 'robocopy' -ArgList $roboArgs
# robocopy 的退出码：0 到 7 都表示成功（例如 1 表示复制了文件），8 及以上才是失败
if ($robo.ExitCode -ge 8) {
    Fail ('复制文件时出错（robocopy 返回代码 {0}）。' -f $robo.ExitCode) -Hints @(
        '常见原因：磁盘空间不足，或者有文件正被其他程序占用。',
        '办法：关闭可能占用这些文件的程序（例如编辑器、杀毒软件的扫描），然后重新运行。'
    ) -Output $robo.Lines
}
Write-Ok '复制完成。'

# 如果你的文件夹自带了另一份 LICENSE，把 GitHub 上原来的 LICENSE 保留下来
$licenseKept = $false
$hasLicenseInHead = Invoke-Git -Dir $script:Repo -GitArgs @('cat-file', '-e', 'HEAD:LICENSE') -DropStderr
if ($hasLicenseInHead.ExitCode -eq 0) {
    $licDiff = Invoke-Git -Dir $script:Repo -GitArgs @('diff', '--quiet', 'HEAD', '--', 'LICENSE') -DropStderr
    if ($licDiff.ExitCode -ne 0) {
        $restore = Invoke-Git -Dir $script:Repo -GitArgs @('checkout', 'HEAD', '--', 'LICENSE')
        if ($restore.ExitCode -ne 0) {
            Fail '无法保留 GitHub 上原来的 LICENSE 文件。' -Output $restore.Lines
        }
        $licenseKept = $true
        Write-Ok '你的文件夹里带有另一份 LICENSE，已保留 GitHub 上原来的 LICENSE（没有被覆盖）。'
    }
}

# =====================================================================
#  第 5 步：显示改动清单
# =====================================================================
Write-Step 5 '检查改动清单（这一步只是看一看，什么都不会推送）'

$add = Invoke-Git -Dir $script:Repo -GitArgs @('add', '-A')
if ($add.ExitCode -ne 0) {
    Fail '登记改动时出错。' -Hints @('办法：请把下面的原始信息发给开发者。') -Output $add.Lines
}

$ns = Invoke-Git -Dir $script:Repo -GitArgs @('diff', '--cached', '--name-status', '--no-renames')
if ($ns.ExitCode -ne 0) {
    Fail '读取改动清单时出错。' -Output $ns.Lines
}
$nsLines = @($ns.Lines | Where-Object { $_ -ne '' })

$newCount = 0
$modCount = 0
$delCount = 0
$otherCount = 0
$bytes = [long]0
$licenseTouched = $false
$readmeModified = $false
$delNames = @()
foreach ($line in $nsLines) {
    $parts = $line -split "`t", 2
    if ($parts.Count -lt 2) { continue }
    $kind = $parts[0].Substring(0, 1)
    $rel = $parts[1]
    if ($rel -eq 'LICENSE') { $licenseTouched = $true }
    if ($kind -eq 'D') { $delCount++; $delNames += $rel; continue }
    if ($kind -eq 'A') { $newCount++ }
    elseif ($kind -eq 'M') {
        $modCount++
        if ($rel -eq 'README.md') { $readmeModified = $true }
    }
    else { $otherCount++ }
    $full = Join-Path $script:Repo $rel
    if (Test-Path -LiteralPath $full -PathType Leaf) {
        $bytes += (Get-Item -LiteralPath $full -Force).Length
    }
}

# 安全检查：任何文件被显示为「已删除」都立即停止
if ($delCount -gt 0) {
    Write-Host ''
    Write-Host ('出问题了：有 {0} 个文件会被删除。' -f $delCount) -ForegroundColor Red
    Write-Host '  本脚本的原则是只新增或替换，绝不删除，所以这里停下来了。' -ForegroundColor Yellow
    foreach ($d in ($delNames | Select-Object -First 15)) { Write-Host ('    将被删除：' + $d) -ForegroundColor DarkGray }
    Write-Host '  办法：请把以上信息发给开发者，不要再继续。' -ForegroundColor Yellow
    Write-Host ''
    Write-Host '没有任何东西被推送，GitHub 和你自己的文件夹都没有被改动。' -ForegroundColor Green
    Write-Host ('临时文件夹（里面只是副本，可以放心删除）：' + $script:WorkDirFull) -ForegroundColor DarkGray
    exit 1
}

if ($nsLines.Count -eq 0) {
    Write-Host ''
    Write-Host '没有发现任何需要发布的改动：你的文件和 GitHub 上的内容已经完全一致。' -ForegroundColor Green
    Write-Host '没有推送任何东西，也不需要再做什么。'
    Write-Host ('临时文件夹（可以放心删除）：' + $script:WorkDirFull) -ForegroundColor DarkGray
    exit 0
}

$st = Invoke-Git -Dir $script:Repo -GitArgs @('status', '--short')
$stLines = @($st.Lines | Where-Object { $_ -ne '' })
Write-Note '改动清单（A=新增，M=修改）：'
foreach ($l in ($stLines | Select-Object -First 40)) { Write-Host ('    ' + $l) }
if ($stLines.Count -gt 40) { Write-Note ('…另有 {0} 项' -f ($stLines.Count - 40)) }

$mb = [math]::Round($bytes / 1MB, 2)
Write-Host ''
Write-Ok ('汇总：新增 {0} 个文件，修改 {1} 个文件，删除 0 个文件；合计约 {2} MB。' -f $newCount, $modCount, $mb)
if ($otherCount -gt 0) { Write-Note ('另有 {0} 项属于其他类型的改动。' -f $otherCount) }
if ((-not $licenseTouched) -or $licenseKept) {
    Write-Note 'LICENSE（开源许可证）保持不变。'
}
if ($readmeModified) {
    Write-Note 'README.md 会被替换为你这份新的版本（GitHub 上原来的旧版本仍可在历史记录里找到）。'
}

# =====================================================================
#  第 6 步：确认、提交、推送
# =====================================================================
Write-Step 6 '确认后提交并推送到 GitHub'
if ($DryRun) {
    Write-Warn '演练模式：不会真正推送。下面会走完提交，但最后只做「模拟推送」。'
}

if (-not $Yes) {
    Write-Host ''
    Write-Host ('即将把以上 {0} 项改动作为 1 个新提交，接在 GitHub 现有历史后面。' -f $nsLines.Count)
    $answer = ''
    try {
        $answer = Read-Host '确认继续吗？输入 yes（或 y、是）后按回车继续；输入其他内容或直接回车则取消'
    }
    catch {
        $answer = ''
    }
    $norm = ([string]$answer).Trim().ToLowerInvariant()
    if (-not (($norm -eq 'yes') -or ($norm -eq 'y') -or ($norm -eq '是'))) {
        Write-Host ''
        Write-Host '已取消，没有任何改动被推送' -ForegroundColor Green
        Write-Host ('临时文件夹（可以放心删除）：' + $script:WorkDirFull) -ForegroundColor DarkGray
        exit 0
    }
}

# 提交时用谁的名字：如果电脑上的 Git 已经设置了姓名和邮箱，就照用；
# 否则借用这个仓库最早那次提交的作者（也就是你自己之前的身份），只用于这一次，不改动电脑上的任何设置。
$cfgName = Get-GitLine -Dir $script:Repo -GitArgs @('config', 'user.name')
$cfgEmail = Get-GitLine -Dir $script:Repo -GitArgs @('config', 'user.email')
$idConfig = @()
if (($cfgName -ne '') -and ($cfgEmail -ne '')) {
    Write-Note ('提交身份：使用电脑上已设置的 {0} <{1}>' -f $cfgName, $cfgEmail)
}
else {
    $firstHash = Get-GitLine -Dir $script:Repo -GitArgs @('rev-list', '--max-parents=0', 'HEAD')
    $histName = ''
    $histEmail = ''
    if ($firstHash -ne '') {
        $histName = Get-GitLine -Dir $script:Repo -GitArgs @('log', '-1', '--format=%an', $firstHash)
        $histEmail = Get-GitLine -Dir $script:Repo -GitArgs @('log', '-1', '--format=%ae', $firstHash)
    }
    if (($histName -eq '') -or ($histEmail -eq '')) {
        Fail '电脑上的 Git 没有设置姓名和邮箱，也没能从仓库历史里找到可用的身份。' -Hints @(
            '办法：请把这条信息发给开发者。'
        )
    }
    $idConfig = @(('user.name=' + $histName), ('user.email=' + $histEmail))
    Write-Note ('提交身份：电脑上的 Git 还没有设置姓名，所以这一次借用仓库最早提交的作者 {0} <{1}>（只用这一次，不会修改电脑上的任何设置）。' -f $histName, $histEmail)
}

$commit = Invoke-Git -Dir $script:Repo -ExtraConfig $idConfig -GitArgs @('commit', '-m', $CommitMessage)
if ($commit.ExitCode -ne 0) {
    Fail '提交时出错。' -Hints @('办法：请把下面的原始信息发给开发者。') -Output $commit.Lines
}
$newHash = Get-GitLine -Dir $script:Repo -GitArgs @('rev-parse', 'HEAD')
$newShort = Get-GitLine -Dir $script:Repo -GitArgs @('rev-parse', '--short', 'HEAD')
$parentHash = Get-GitLine -Dir $script:Repo -GitArgs @('rev-parse', 'HEAD~1')
if (($parentHash -eq '') -or ($parentHash -ne $script:HeadBefore)) {
    Fail '安全检查没有通过：新提交没有正确地接在 GitHub 现有历史后面。' -Hints @('为安全起见已停止，请把这条信息发给开发者。')
}
Write-Ok ('已在临时副本里生成新提交 {0}，它接在 {1} 后面。' -f $newShort, $shortBefore)

# 普通推送：从不使用任何强制选项
if ($DryRun) {
    $pushArgs = @('push', '--dry-run', 'origin', $Branch)
    Write-Note '正在做模拟推送（演练模式，不会真正推送）。请稍候……'
}
else {
    $pushArgs = @('push', 'origin', $Branch)
    Write-Note '正在推送到 GitHub。如果弹出登录窗口，请按提示登录（用拥有该仓库权限的 GitHub 账号）。请稍候……'
}
$push = Invoke-Git -Dir $script:Repo -GitArgs $pushArgs
if ($push.ExitCode -ne 0) {
    $pushHints = Get-GitHints -Text ($push.Lines -join "`n") -Phase 'push'
    $msg = '推送没有成功。'
    if ($DryRun) { $msg = '模拟推送没有成功。' }
    Fail $msg -Hints $pushHints -Output $push.Lines -Reassure '没有任何东西被推送到 GitHub，GitHub 上的原有内容完好无损；你自己的文件夹也没有被改动。'
}
foreach ($l in ($push.Lines | Where-Object { $_ -ne '' } | Select-Object -Last 8)) {
    Write-Host ('    ' + $l) -ForegroundColor DarkGray
}

$webUrl = $RepoUrl -replace '\.git$', ''
Write-Host ''
if ($DryRun) {
    Write-Host '演练完成：一切顺利，但这一次没有真正推送。' -ForegroundColor Green
    Write-Host ('  如果是真正推送，将会生成的提交：' + $newHash)
}
else {
    Write-Host '全部完成，已成功推送到 GitHub。' -ForegroundColor Green
    Write-Host ('  提交编号：' + $newHash)
    Write-Host ('  仓库网址：' + $webUrl)
}
Write-Host ('  临时文件夹（里面只是副本，可以放心删除）：' + $script:WorkDirFull) -ForegroundColor DarkGray
exit 0
