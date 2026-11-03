"""First-install only. Run as root after placing the reviewed source release.

Does not expose a socket, change Nginx or read another application's data.
The private environment and randomly generated review access stay on the host.
"""
import os
import pwd
import secrets
import subprocess
import sys
from pathlib import Path

release = Path(sys.argv[1]).resolve()
if os.geteuid() != 0 or release.parent != Path('/opt/orientir-demo/releases'):
    raise SystemExit('Invalid installation context')
state = Path('/var/lib/orientir-demo')
env_file = Path('/etc/orientir-demo.env')
if env_file.exists() or state.exists():
    raise SystemExit('Existing installation retained; first-install refused')
account = pwd.getpwnam('orientir-demo')
def unprivileged():
    os.setgroups([])
    os.setgid(account.pw_gid)
    os.setuid(account.pw_uid)

python = str(release / '.venv/bin/python')
# Check runtime traversal/execution before creating private persistent state.
subprocess.run([python, '-c', 'pass'], cwd=release, preexec_fn=unprivileged, check=True)
os.umask(0o077)
state.mkdir(mode=0o700)
os.chown(state, account.pw_uid, account.pw_gid)
values = {'MENTOR_PROFILE': 'vps-demo', 'MENTOR_PUBLIC_HOST': 'orientir.178-255-126-110.sslip.io', 'MENTOR_STATE_DIR': str(state), 'MENTOR_SECRET_KEY': secrets.token_urlsafe(64), 'PYTHONDONTWRITEBYTECODE': '1'}
with env_file.open('x', encoding='ascii') as stream:
    stream.write(''.join(k + '=' + v + '\n' for k, v in values.items()))
env = {**os.environ, **values}
subprocess.run([python, 'manage.py', 'collectstatic', '--noinput'], cwd=release, env=env, check=True)

for command in [('migrate', '--noinput'), ('seed_demo',), ('check', '--deploy'), ('backup_mentor',)]:
    subprocess.run([python, 'manage.py', *command], cwd=release, env=env, preexec_fn=unprivileged, check=True)
print('First installation initialized; credentials retained in private host state.')
