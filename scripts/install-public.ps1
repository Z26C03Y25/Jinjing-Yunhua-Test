# Independent public-repository installer. Never stages, commits or pushes Git.
[CmdletBinding()]
param(
    [string]$Server,
    [string]$User = 'root',
    [int]$Port = 22,
    [string]$RemoteDirectory = 'code/Jinjing-Yunhua-Test',
    [int]$WebPort = 80,
    [ValidateSet('0.0.0.0','127.0.0.1')][string]$Bind = '0.0.0.0',
    [string]$Project = 'jinjing-yunhua',
    [string]$BackendImage = 'jinjing-backend:stage1',
    [switch]$UseDownloadedCode
)
$ErrorActionPreference = 'Stop'
$ssh = Join-Path $env:WINDIR 'System32/OpenSSH/ssh.exe'
if (-not (Test-Path -LiteralPath $ssh)) { throw '本机需要 Windows OpenSSH 客户端。' }
if (-not $Server) { $Server = Read-Host '请输入新 Ubuntu 服务器 IP' }
$Server = $Server.Trim()
if ($Server -notmatch '^[a-zA-Z0-9][a-zA-Z0-9.:-]*$' -or $User -notmatch '^[a-zA-Z_][a-zA-Z0-9_-]*$') { throw '服务器地址或用户名无效。' }
if ($Port -lt 1 -or $Port -gt 65535 -or $WebPort -lt 1 -or $WebPort -gt 65535) { throw '端口无效。' }
if ($RemoteDirectory -notmatch '^[a-zA-Z0-9_-]+(/[a-zA-Z0-9_-]+)*$' -or $Project -notmatch '^[a-z0-9][a-z0-9_-]*$' -or $BackendImage -notmatch '^[a-z0-9][a-z0-9./:_-]*$') { throw '目录、项目名或镜像名无效。' }
$shellPath = Join-Path $PSScriptRoot 'install-public.sh'
$pythonPath = Join-Path $PSScriptRoot 'install-public.py'
foreach ($path in @($shellPath,$pythonPath)) { if (-not (Test-Path -LiteralPath $path)) { throw "缺少安装组件：$path" } }
$python64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($pythonPath))
$body = [IO.File]::ReadAllText($shellPath).Replace("`r`n", "`n")
$body = $body.Replace('__PYTHON64__',$python64).Replace('__DIRECTORY__',$RemoteDirectory).Replace('__WEBPORT__',"$WebPort").Replace('__BIND__',$Bind).Replace('__PROJECT__',$Project).Replace('__IMAGE__',$BackendImage)
$extra = if ($UseDownloadedCode) { '--use-downloaded-code' } else { '' }
$body = $body.Replace('__EXTRA__',$extra)
$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($body))
Write-Host '这是独立安装脚本，不会提交代码，不需要 GitHub 密钥。'
Write-Host '请在随后 SSH 的 password 提示中输入服务器密码（不显示字符）。'
Write-Host '首次连接需核对服务器指纹并输入 yes；连接后会引导设置系统密码。'
& $ssh -t -p $Port -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 "$User@$Server" "echo $encoded | base64 -d | bash"
if ($LASTEXITCODE -ne 0) { throw '自动安装未完成，请查看上方具体错误；现有数据不会被自动删除。' }
Write-Host "安装完成，浏览器访问 http://${Server}:$WebPort/ 。云安全组需允许此业务端口。"
