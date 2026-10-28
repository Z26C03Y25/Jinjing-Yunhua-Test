# CMD entry point: scripts\sync-remote.cmd
[CmdletBinding()]
param(
    [string]$Server,
    [string]$User,
    [int]$Port = 22,
    [string]$RemoteDirectory = 'code/Jinjing-Yunhua-Test',
    [string]$Message = 'chore: sync local changes to Ubuntu',
    [switch]$Deploy,
    [switch]$SkipCommit
)
$ErrorActionPreference = 'Stop'

function Invoke-Git {
    param([string[]]$Arguments)
    & git @Arguments
    if ($LASTEXITCODE -ne 0) { throw "git command failed: $($Arguments -join ' ')" }
}

if (-not $Server) { $Server = Read-Host '请输入 Ubuntu 服务器 IP' }
if (-not $User) {
    $User = Read-Host '请输入 SSH 用户名（直接回车使用 root）'
    if (-not $User) { $User = 'root' }
}
if ($Server -notmatch '^[a-zA-Z0-9][a-zA-Z0-9.:-]*$') { throw 'Invalid server address' }
if ($User -notmatch '^[a-zA-Z0-9_][a-zA-Z0-9_-]*$') { throw 'Invalid SSH username' }
if ($Port -lt 1 -or $Port -gt 65535) { throw 'Invalid SSH port' }
# Deliberately limit paths: relative to the remote home directory, no traversal.
if ($RemoteDirectory -notmatch '^[a-zA-Z0-9_-]+(/[a-zA-Z0-9_-]+)*$') {
    throw 'RemoteDirectory must be a simple relative path, for example projects/Jinjing-Yunhua-Test'
}

Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    $repo = 'https://github.com/Z26C03Y25/Jinjing-Yunhua-Test.git'
    $origin = (& git remote get-url origin)
    if ($LASTEXITCODE -ne 0 -or $origin.Trim() -ne $repo) { throw 'Unexpected origin URL' }
    $branch = (& git symbolic-ref --short HEAD)
    if ($LASTEXITCODE -ne 0 -or $branch -notmatch '^[a-zA-Z0-9_][a-zA-Z0-9_./-]*$') { throw 'A named branch is required' }
    if (-not $SkipCommit) {
        foreach ($identity in @(
            @{ Key = 'user.name'; Prompt = '请输入 Git 提交姓名（例如你的姓名或 GitHub 用户名）' },
            @{ Key = 'user.email'; Prompt = '请输入 Git 提交邮箱（可使用 GitHub 的 noreply 邮箱）' }
        )) {
            $configured = & git config --get $identity.Key
            if (-not $configured -or -not "$configured".Trim()) {
                Write-Host "当前缺少 $($identity.Key)，填写后仅保存到此仓库。"
                do {
                    $value = Read-Host $identity.Prompt
                    if (-not $value -or -not $value.Trim()) { Write-Host '此项不能为空，请重新输入。' }
                } while (-not $value -or -not $value.Trim())
                Invoke-Git -Arguments @('config', '--local', $identity.Key, $value.Trim())
            }
        }
        Write-Host '正在提交本地修改（遵循 .gitignore）...'
        Invoke-Git -Arguments @('add', '--all')
        & git diff --cached --quiet
        if ($LASTEXITCODE -eq 1) { Invoke-Git -Arguments @('commit', '-m', $Message) }
        elseif ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes' }
    }
    $revision = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw '无法读取本地提交版本' }
    $pushed = $false
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        Write-Host "正在推送到 GitHub（第 $attempt/3 次），请等待服务器确认..."
        & git -c http.version=HTTP/1.1 -c http.connectTimeout=20 -c http.lowSpeedLimit=1 -c http.lowSpeedTime=45 push origin "HEAD:refs/heads/$branch"
        if ($LASTEXITCODE -eq 0) { $pushed = $true; break }
        Write-Host '推送连接异常，正在核对 GitHub 分支版本...'
        $remoteHead = & git -c http.version=HTTP/1.1 -c http.connectTimeout=20 -c http.lowSpeedLimit=1 -c http.lowSpeedTime=45 ls-remote --exit-code origin "refs/heads/$branch"
        if ($LASTEXITCODE -eq 0 -and $remoteHead -and ($remoteHead -split '\s+')[0] -eq $revision) {
            Write-Host '已确认 GitHub 收到了本次提交，继续同步服务器。'
            $pushed = $true
            break
        }
        if ($attempt -lt 3) { Start-Sleep -Seconds 3 }
    }
    if (-not $pushed) { throw '推送失败或无法确认远程版本。请检查 GitHub 网络连接，稍后使用 -SkipCommit 重试。' }
    $question = Get-ChildItem -LiteralPath (Join-Path $PWD '题目') -Filter '*.docx' -File | Select-Object -First 1
    if (-not $question) { throw 'Question DOCX was not found' }
    $questionHash = (Get-FileHash -LiteralPath $question.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $deployValue = if ($Deploy) { '1' } else { '0' }
    $remoteScript = @'
set -eu
repo='__REPO__'
branch='__BRANCH__'
target="$HOME/__DIRECTORY__"
expected='__REVISION__'
command -v git >/dev/null || { echo 'Install git on Ubuntu first'; exit 1; }
# Keep server-wide URL rewrites (HTTPS -> SSH) out of this sync operation.
# These environment settings only apply to this remote shell, not saved config.
echo '使用独立 Git 配置，通过 HTTPS 同步（不读取服务器全局 URL 改写）...'
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_NOSYSTEM=1
export GIT_TERMINAL_PROMPT=0
mkdir -p "$(dirname "$target")"
if [ ! -e "$target" ]; then
    echo '首次同步：正在克隆仓库...'
    GIT_TERMINAL_PROMPT=0 git clone --branch "$branch" -- "$repo" "$target"
fi
cd "$target"
[ "$(git rev-parse --show-toplevel)" = "$target" ] || { echo 'Target is not a repository root'; exit 1; }
[ "$(git remote get-url origin)" = "$repo" ] || { echo 'Unexpected remote origin'; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo 'Remote has local changes; resolve them first'; exit 1; }
git checkout "$branch"
echo '正在拉取远程代码...'
GIT_TERMINAL_PROMPT=0 git pull --ff-only origin "$branch"
[ "$(git rev-parse HEAD)" = "$expected" ] || { echo 'Revision mismatch; refusing deployment'; exit 1; }
python3 - <<'PY'
import hashlib, pathlib
files = list(pathlib.Path('题目').glob('*.docx'))
assert any(hashlib.sha256(p.read_bytes()).hexdigest() == '__HASH__' for p in files), 'Question file SHA256 mismatch'
print('校验成功：服务器题目文件与本地一致')
PY
echo "同步成功，服务器版本：$expected"
echo "代码目录：$target"
if [ '__DEPLOY__' = 1 ]; then
    docker compose version
    docker compose config --quiet
    docker compose up -d --build
    docker compose ps
fi
'@
    $remoteScript = $remoteScript.Replace('__REPO__', $repo).Replace('__BRANCH__', $branch).Replace('__DIRECTORY__', $RemoteDirectory).Replace('__REVISION__', $revision).Replace('__HASH__', $questionHash).Replace('__DEPLOY__', $deployValue).Replace("`r`n", "`n")
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remoteScript))
    Write-Host "即将连接 $User@$Server，代码目录：~/$RemoteDirectory"
    Write-Host '请输入服务器密码：请在随后 SSH 的 password 提示处输入，输入时不显示字符，按回车确认。'
    Write-Host '密码不会保存。首次连接请先核对云控制台中的主机指纹，确认后输入 yes。'
    & ssh -t -p $Port -o ConnectTimeout=20 -o ServerAliveInterval=15 "$User@$Server" "echo $encoded | base64 -d | bash"
    if ($LASTEXITCODE -ne 0) { throw 'Remote synchronization or deployment failed' }
} finally {
    Pop-Location
}
