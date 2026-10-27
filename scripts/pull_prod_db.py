"""Copia la base de producción (Railway) a la base local SQLite.

Producción solo se LEE (dumpdata). La base local se reemplaza completa;
la anterior queda respaldada en .local/.

Uso (desde C:\\dev\\hoteltickets, con `railway link` hecho):
    .\\venv\\Scripts\\python.exe scripts\\pull_prod_db.py
"""
import datetime
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent.parent
LOCAL = BASE / '.local'
PY = sys.executable


def railway_cmd():
    """`railway` puede no estar en el PATH de PowerShell; se busca en la carpeta global de npm."""
    found = shutil.which('railway')
    if found:
        return found
    dirs = [Path(os.environ.get('APPDATA', '')) / 'npm', Path.home() / 'AppData' / 'Roaming' / 'npm']
    # Instalado desde la app de Claude (MSIX): queda en su AppData virtualizado.
    dirs += sorted((Path.home() / 'AppData' / 'Local' / 'Packages').glob('Claude_*/LocalCache/Roaming/npm'))
    try:
        prefix = subprocess.run('npm prefix -g', shell=True, capture_output=True, text=True).stdout.strip()
        if prefix:
            dirs.append(Path(prefix))
    except OSError:
        pass
    for d in dirs:
        if (d / 'railway.cmd').exists():
            return str(d / 'railway.cmd')
    sys.exit('No se encontró el CLI de Railway. Buscado en: ' + ', '.join(str(d) for d in dirs))


def prod_url(environment='production'):
    """URL pública de la base del ambiente indicado (explícito: no depende de `railway link`)."""
    out = subprocess.run([railway_cmd(), 'variables', '-s', 'Postgres', '-e', environment, '--json'],
                         capture_output=True, text=True, cwd=BASE, check=True).stdout
    url = json.loads(out).get('DATABASE_PUBLIC_URL')
    if not url:
        sys.exit(f'No se encontró DATABASE_PUBLIC_URL en el Postgres de {environment}.')
    return _with_hostaddr(url)


def _with_hostaddr(url):
    """Si el DNS local no resuelve el host (p. ej. el router cacheó un 'no existe' de un proxy
    recién creado), se resuelve con DNS público y se pasa como `hostaddr` a libpq."""
    host = urlparse(url).hostname
    try:
        socket.getaddrinfo(host, None)
        return url
    except socket.gaierror:
        pass
    out = subprocess.run(['nslookup', host, '8.8.8.8'], capture_output=True, text=True).stdout
    ips = re.findall(r'(\d+\.\d+\.\d+\.\d+)', out.split(host, 1)[-1])
    if not ips:
        sys.exit(f'No se pudo resolver {host}.')
    return url + ('&' if '?' in url else '?') + f'hostaddr={ips[0]}'


def manage(*args, env=None):
    subprocess.run([PY, 'manage.py', *args], cwd=BASE, env=env, check=True)


def main():
    LOCAL.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    dump = LOCAL / f'prod-{stamp}.json'

    print('1/3 Leyendo producción...')
    env = {**os.environ, 'DATABASE_URL': prod_url()}
    with open(dump, 'w', encoding='utf-8') as fh:
        subprocess.run([PY, '-X', 'utf8', 'manage.py', 'dumpdata', '--natural-foreign', '--natural-primary',
                        '-e', 'contenttypes', '-e', 'auth.permission',
                        '-e', 'sessions', '-e', 'admin.logentry', '--indent', '1'],
                       cwd=BASE, env=env, stdout=fh, check=True)

    print('2/3 Recreando base local...')
    env_local = {**os.environ, 'DATABASE_URL': ''}
    db = BASE / 'db.sqlite3'
    if db.exists():
        shutil.move(db, LOCAL / f'db-local-{stamp}.sqlite3')
    manage('migrate', '--no-input', env=env_local)

    print('3/3 Cargando datos...')
    manage('loaddata', str(dump), env=env_local)
    print(f'Listo. Copia de producción en db.sqlite3 (dump: {dump.name})')


if __name__ == '__main__':
    main()
