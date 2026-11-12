#!/usr/bin/env python3
"""Run as root on the existing staging monitoring EC2; no secrets are embedded."""
from pathlib import Path
from datetime import datetime, timezone
import shutil
import subprocess
import time

root = Path('/opt/monitoring-staging')
compose = root / 'compose.yml'
nginx = Path('/etc/nginx/sites-enabled/staging-grafana').resolve()
backup = root / 'backups' / ('eks-metrics-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir(parents=True)
backup.chmod(0o700)
for path in [compose, nginx]:
    shutil.copy2(path, backup / path.name)

text = compose.read_text()
if '--web.enable-remote-write-receiver' not in text:
    anchor = '      - --storage.tsdb.retention.size=4GB'
    if text.count(anchor) != 1:
        raise SystemExit('Unexpected Prometheus command layout; inspect before changing.')
    text = text.replace(anchor, anchor + '\n      - --web.enable-remote-write-receiver')
compose.write_text(text)
text = nginx.read_text()
if 'location = /api/v1/write' not in text:
    anchor = '    location / {'
    if text.count(anchor) != 1:
        raise SystemExit('Unexpected Nginx layout; inspect before changing.')
    location = '''    # EKS metrics ingestion over private TLS; Grafana access rules remain separate.
    location = /api/v1/write {
        allow 10.20.0.0/16;
        deny all;
        limit_except POST { deny all; }
        client_max_body_size 10m;
        proxy_pass http://127.0.0.1:9090/api/v1/write;
        proxy_read_timeout 30s;
    }

'''
    text = text.replace(anchor, location + anchor)
nginx.write_text(text)
cmd = ['docker', 'compose', '--project-directory', str(root), '-p', 'kgb-staging-monitoring', '-f', str(compose)]
try:
    subprocess.run(cmd + ['config', '-q'], check=True)
    subprocess.run(['nginx', '-t'], check=True)
except subprocess.CalledProcessError:
    shutil.copy2(backup / compose.name, compose)
    shutil.copy2(backup / nginx.name, nginx)
    raise
subprocess.run(cmd + ['up', '-d', '--no-deps', 'prometheus'], check=True)
for _ in range(30):
    result = subprocess.run(['curl', '-fsS', '--max-time', '2', 'http://127.0.0.1:9090/-/ready'], capture_output=True)
    if result.returncode == 0:
        break
    time.sleep(1)
else:
    raise SystemExit('Prometheus did not become ready; inspect container logs and backup.')
subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
print('Prometheus ready; private TLS ingestion enabled. Backup:', backup)
