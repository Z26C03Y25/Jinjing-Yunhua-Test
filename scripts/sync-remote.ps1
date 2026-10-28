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
$windowsSsh = Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'
if (-not (Test-Path -LiteralPath $windowsSsh)) { throw '未找到 Windows OpenSSH，请安装 Windows 可选功能 OpenSSH 客户端。' }
$keyPath = Join-Path $env:USERPROFILE '.ssh\id_ed25519'
$knownHostsPath = Join-Path $env:USERPROFILE '.ssh\known_hosts'
$gitSshCommand = '"' + $windowsSsh.Replace('\', '/') + '" -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o IdentitiesOnly=yes -i "' + $keyPath.Replace('\', '/') + '" -o UserKnownHostsFile="' + $knownHostsPath.Replace('\', '/') + '"'

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
    $sshRepo = 'git@github.com:Z26C03Y25/Jinjing-Yunhua-Test.git'
    $origin = (& git remote get-url origin)
    if ($LASTEXITCODE -ne 0 -or $origin.Trim() -notin @($repo, $sshRepo)) { throw 'Unexpected origin URL' }
    Invoke-Git -Arguments @('remote', 'set-url', 'origin', $sshRepo)
    Write-Host '先直接验证 GitHub SSH：首次连接请核对主机指纹，然后输入 yes 并回车；如密钥有口令，请按提示输入。'
    & $windowsSsh -T -o ConnectTimeout=20 -o IdentitiesOnly=yes -i $keyPath -o "UserKnownHostsFile=$knownHostsPath" git@github.com
    # GitHub returns 1 even after successful authentication (no shell access).
    if ($LASTEXITCODE -ne 1 -and $LASTEXITCODE -ne 0) {
        throw 'GitHub SSH 连接失败，请查看上方主机确认、网络或密钥错误。'
    }
    Write-Host '本地 GitHub 连接已切换为 SSH，正在检查仓库访问权限...'
    & git -c "core.sshCommand=$gitSshCommand" ls-remote --exit-code origin HEAD
    if ($LASTEXITCODE -ne 0) {
        throw 'GitHub SSH 验证失败。已使用 Windows OpenSSH；请检查本机 id_ed25519 密钥及 GitHub 中对应的公钥，并查看上方具体错误。'
    }
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
        & git -c "core.sshCommand=$gitSshCommand" push origin "HEAD:refs/heads/$branch"
        if ($LASTEXITCODE -eq 0) { $pushed = $true; break }
        Write-Host '推送连接异常，正在核对 GitHub 分支版本...'
        $remoteHead = & git -c "core.sshCommand=$gitSshCommand" ls-remote --exit-code origin "refs/heads/$branch"
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
repo='git@github.com:Z26C03Y25/Jinjing-Yunhua-Test.git'
https_repo='__REPO__'
branch='__BRANCH__'
target="$HOME/__DIRECTORY__"
expected='__REVISION__'
command -v git >/dev/null || { echo 'Install git on Ubuntu first'; exit 1; }
# Keep server-wide URL rewrites (HTTPS -> SSH) out of this sync operation.
# These environment settings only apply to this remote shell, not saved config.
echo '服务器通过专用 SSH Deploy key 拉取仓库...'
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_NOSYSTEM=1
export GIT_TERMINAL_PROMPT=0
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
key="$HOME/.ssh/jinjing_yunhua_deploy"
if [ ! -f "$key" ]; then
    ssh-keygen -t ed25519 -N '' -C 'Jinjing-Yunhua read-only deploy key' -f "$key"
fi
export GIT_SSH_COMMAND="ssh -i $key -o IdentitiesOnly=yes -o ConnectTimeout=20"
if ! git ls-remote "$repo" HEAD; then
    echo '请把下面整行公钥添加到 GitHub 仓库 Settings -> Deploy keys -> Add deploy key：'
    echo 'https://github.com/Z26C03Y25/Jinjing-Yunhua-Test/settings/keys'
    echo '只需读取权限，不要勾选 Allow write access。'
    cat "$key.pub"
    printf '\n添加完成后按回车继续，或 Ctrl+C 退出：'
    read -r answer </dev/tty
    git ls-remote "$repo" HEAD || { echo 'Deploy key 验证失败，请检查是否添加到正确仓库'; exit 1; }
fi
mkdir -p "$(dirname "$target")"
if [ ! -e "$target" ]; then
    echo '首次同步：正在克隆仓库...'
    GIT_TERMINAL_PROMPT=0 git clone --branch "$branch" -- "$repo" "$target"
fi
cd "$target"
[ "$(git rev-parse --show-toplevel)" = "$target" ] || { echo 'Target is not a repository root'; exit 1; }
existing_origin=$(git remote get-url origin)
if [ "$existing_origin" = "$https_repo" ]; then
    git remote set-url origin "$repo"
elif [ "$existing_origin" != "$repo" ]; then
    echo 'Unexpected remote origin'; exit 1
fi
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
    if ! docker compose up -d --build --wait --wait-timeout 120; then
        docker compose ps
        docker compose logs --tail 80
        exit 1
    fi
    docker compose ps
    echo '部署完成，Web 健康检查已通过。默认仅监听服务器 127.0.0.1:8080。'
fi
'@
    $remoteScript = $remoteScript.Replace('__REPO__', $repo).Replace('__BRANCH__', $branch).Replace('__DIRECTORY__', $RemoteDirectory).Replace('__REVISION__', $revision).Replace('__HASH__', $questionHash).Replace('__DEPLOY__', $deployValue).Replace("`r`n", "`n")
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remoteScript))
    Write-Host "即将连接 $User@$Server，代码目录：~/$RemoteDirectory"
    Write-Host '请输入服务器密码：请在随后 SSH 的 password 提示处输入，输入时不显示字符，按回车确认。'
    Write-Host '密码不会保存。首次连接请先核对云控制台中的主机指纹，确认后输入 yes。'
    & $windowsSsh -t -p $Port -o ConnectTimeout=20 -o ServerAliveInterval=15 "$User@$Server" "echo $encoded | base64 -d | bash"
    if ($LASTEXITCODE -ne 0) { throw 'Remote synchronization or deployment failed' }
} finally {
    Pop-Location
}
