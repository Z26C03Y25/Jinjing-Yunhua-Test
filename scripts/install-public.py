"""Ubuntu/root bootstrap of a public HTTPS repository; no Git write operations."""
import argparse
import base64
import getpass
import json
import os
import pathlib
import socket
import subprocess
import tempfile
import time
import urllib.request

REPOSITORY = 'https://github.com/Z26C03Y25/Jinjing-Yunhua-Test.git'


def run(command, cwd=None, capture=False, timeout=900, env=None):
    return subprocess.run(command, cwd=cwd, env=env, check=True, timeout=timeout,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None,
                          text=True, stdin=subprocess.DEVNULL).stdout


def dotenv_quote(value):
    if any(c in value for c in ('\n', '\r', '\0')):
        raise ValueError('密码不能包含换行或空字符')
    return "'" + value.replace("'", "\\'") + "'"


def save_configuration(target, analyst, viewer, args):
    if (target / '.env').exists():
        return False
    values = {'APP_PASSWORD': analyst, 'VIEWER_PASSWORD': viewer,
              'WEB_PORT': str(args.web_port), 'WEB_BIND': args.bind,
              'COMPOSE_PROJECT_NAME': args.project, 'BACKEND_IMAGE': args.backend_image}
    temporary = target / ('.env.install-' + os.urandom(8).hex())
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(''.join(key + '=' + dotenv_quote(value) + '\n' for key, value in values.items()))
        os.replace(temporary, target / '.env')
    finally:
        temporary.unlink(missing_ok=True)
    return True


def read_password(label, optional=False):
    while True:
        value = getpass.getpass(label)
        if optional and not value:
            return ''
        if len(value) < 8 or any(c in value for c in ('\n','\r','\0')):
            print('请至少设置8个字符，不支持换行或空字符。', flush=True)
            continue
        if value != getpass.getpass('请再次输入确认：'):
            print('两次输入不一致，请重新设置。', flush=True)
            continue
        return value


def prepare_repository(target, update=True):
    if target.is_symlink():
        raise RuntimeError('安装目标不能是符号链接')
    env = dict(os.environ, GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_SYSTEM='/dev/null', GIT_TERMINAL_PROMPT='0')
    if not target.exists():
        if not update:
            raise RuntimeError('没有已下载的代码，请先正常运行安装脚本')
        for attempt in range(3):
            with tempfile.TemporaryDirectory(prefix='.jinjing-clone-', dir=target.parent) as folder:
                candidate = pathlib.Path(folder) / 'repository'
                try:
                    run(['git','-c','http.version=HTTP/1.1','-c','http.lowSpeedLimit=1','-c','http.lowSpeedTime=30',
                         'clone','--branch','main',REPOSITORY,str(candidate)], env=env, timeout=180)
                    candidate.rename(target)
                    break
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                    if attempt == 2:
                        raise RuntimeError('公开仓库克隆失败，请检查GitHub网络；未要求GitHub密钥')
                    time.sleep(2)
    else:
        if not (target / '.git').is_dir():
            raise RuntimeError('目标目录存在且不是Git仓库，拒绝覆盖')
        origin = run(['git','remote','get-url','origin'], cwd=target, capture=True, env=env).strip()
        if origin not in (REPOSITORY, 'git@github.com:Z26C03Y25/Jinjing-Yunhua-Test.git'):
            raise RuntimeError('目标目录属于其他仓库，拒绝修改')
        if run(['git','status','--porcelain','--untracked-files=no'], cwd=target, capture=True, env=env).strip():
            raise RuntimeError('服务器存在已修改的跟踪文件，拒绝覆盖')
        run(['git','remote','set-url','origin',REPOSITORY], cwd=target, env=env)
        for attempt in range(3 if update else 0):
            try:
                run(['git','-c','http.version=HTTP/1.1','-c','http.lowSpeedLimit=1','-c','http.lowSpeedTime=30',
                     'pull','--ff-only','origin','main'], cwd=target, env=env, timeout=180)
                break
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                if attempt == 2:
                    raise RuntimeError('公开仓库更新失败，旧配置和数据保持不变')
                time.sleep(2)
    run(['git','check-ignore','--quiet','.env'], cwd=target, env=env)
    tracked = subprocess.run(['git','ls-files','--error-unmatch','.env'], cwd=target, env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if tracked.returncode == 0:
        raise RuntimeError('.env被Git跟踪，拒绝写入任何密码')
    # umask 077 protects credentials but Git checkout files must be readable by
    # the non-root backend and Nginx workers. Only tracked PUBLIC files change.
    tracked_files = run(['git','ls-files','-z'], cwd=target, capture=True, env=env)
    for relative in tracked_files.split('\0'):
        if not relative:
            continue
        path = target / relative
        if path.is_symlink() or target.resolve() not in path.resolve().parents:
            raise RuntimeError('源码含越界或符号链接，拒绝修改权限')
        if path.is_file():
            path.chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)
        parent = path.parent
        while parent != target.parent:
            parent.chmod(0o755)
            if parent == target:
                break
            parent = parent.parent


def prepare_image(image):
    if subprocess.run(['docker','image','inspect',image], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        return
    for source in ('m.daocloud.io/docker.io/library/' + image, image):
        for attempt in range(2):
            try:
                run(['docker','pull',source], timeout=180)
                if source != image:
                    run(['docker','tag',source,image])
                return
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                print('镜像入口暂不可用，正在重试或切换入口…', flush=True)
    raise RuntimeError('镜像下载失败；未停止现有服务，修复网络后可直接重试')


def install(args):
    import fcntl
    target = pathlib.Path.home() / args.directory
    target.parent.mkdir(parents=True, exist_ok=True)
    with (target.parent / ('.' + target.name + '.install.lock')).open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('另一个安装任务正在执行，请勿重复启动')
        prepare_repository(target, not args.use_downloaded_code)
        if args.use_downloaded_code:
            print('按明确指定使用已下载的干净代码，本次不查询GitHub新版本。', flush=True)
        compose = ['docker','compose','--project-name',args.project,'--env-file',str(target / '.env')]
        analyst = viewer = None
        created_configuration = False
        if (target / '.env').is_symlink():
            raise RuntimeError('.env不能是符号链接，拒绝修改权限或写入密码')
        if not (target / '.env').exists():
            print('请设置系统登录密码（与服务器SSH密码分开，输入不回显）。', flush=True)
            analyst = read_password('分析员密码：')
            viewer = read_password('只读账户密码（直接回车禁用只读账户）：', optional=True)
            created_configuration = save_configuration(target, analyst, viewer, args)
        else:
            os.chmod(target / '.env', 0o600)
            print('检测到已有.env，保留系统密码和配置。', flush=True)
        run(compose + ['config','--quiet'], cwd=target, capture=True)
        config = json.loads(run(compose + ['config','--format','json'], cwd=target, capture=True))
        # Config JSON escapes '$' for reserialization; --environment gives the
        # actual interpolation inputs without changing the configured password.
        resolved = run(compose + ['config','--environment'], cwd=target, capture=True)
        environment = dict(line.split('=',1) for line in resolved.splitlines() if '=' in line)
        if analyst is not None and (environment['APP_PASSWORD'] != analyst or environment.get('VIEWER_PASSWORD','') != viewer):
            if created_configuration:
                (target / '.env').unlink()
            raise RuntimeError('密码特殊字符编码校验失败，拒绝启动；密码未输出')
        port = int(config['services']['web']['ports'][0]['published'])
        bind = config['services']['web']['ports'][0].get('host_ip','0.0.0.0')
        own_web = run(compose + ['ps','-q','web'], cwd=target, capture=True).strip()
        if not own_web:
            with socket.socket() as probe:
                try:
                    probe.bind((bind,port))
                except OSError:
                    raise RuntimeError('业务端口已被其他程序占用，未停止任何其他服务')
        prepare_image('debian:12.9-slim')
        prepare_image(config['services']['web']['image'])
        revision = run(['git','rev-parse','HEAD'], cwd=target, capture=True).strip()
        backend_image = config['services']['backend']['image']
        print('正在构建后端，请等待软件包安装；构建失败不会下架旧服务。', flush=True)
        run(['docker','build','--pull=false','--progress=plain','--label','org.opencontainers.image.revision='+revision,
             '-f','backend/Dockerfile','-t',backend_image,'.'], cwd=target, timeout=1800)
        run(compose + ['down','--remove-orphans'], cwd=target)
        run(compose + ['up','-d','--no-build','--pull','never','--wait','--wait-timeout','120'], cwd=target, timeout=180)
        if bind == '0.0.0.0' and pathlib.Path('/usr/sbin/ufw').exists():
            firewall = run(['/usr/sbin/ufw','status'], capture=True)
            if 'Status: active' in firewall:
                run(['/usr/sbin/ufw','allow',str(port)+'/tcp'])
        credential = base64.b64encode(('analyst:'+environment['APP_PASSWORD']).encode()).decode()
        request = urllib.request.Request('http://127.0.0.1:'+str(port)+'/api/me',
                                         headers={'Authorization':'Basic '+credential,'X-Requested-With':'XMLHttpRequest'})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=10) as response:
            if json.load(response).get('readonly') is not False:
                raise RuntimeError('系统登录验证失败')
        run(compose + ['ps'], cwd=target)
        reports = target / '.runtime-reports'
        reports.mkdir(exist_ok=True)
        (reports / 'public-install.json').write_text(json.dumps({
            'completed_at_epoch': time.time(), 'source_revision': revision,
            'source_url': REPOSITORY, 'project': args.project, 'web_port': port,
            'login_verified': True, 'password_file_mode': oct((target / '.env').stat().st_mode & 0o777),
            'passwords_committed': False}, indent=2), encoding='utf-8')
        print('安装及登录验证通过。版本：'+revision, flush=True)
        print('密码仅保存到服务器 '+str(target / '.env')+'（权限600），未提交到Git。', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', default='code/Jinjing-Yunhua-Test')
    parser.add_argument('--web-port', type=int, default=80)
    parser.add_argument('--bind', default='0.0.0.0')
    parser.add_argument('--project', default='jinjing-yunhua')
    parser.add_argument('--backend-image', default='jinjing-backend:stage1')
    parser.add_argument('--use-downloaded-code', action='store_true')
    arguments = parser.parse_args()
    if pathlib.PurePosixPath(arguments.directory).is_absolute() or '..' in pathlib.PurePosixPath(arguments.directory).parts:
        parser.error('安装目录必须是用户目录下的相对路径')
    try:
        install(arguments)
    except KeyboardInterrupt:
        raise SystemExit('安装已取消，未删除业务数据。')
    except (RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, ValueError) as exc:
        raise SystemExit('安装未完成：'+str(exc))
