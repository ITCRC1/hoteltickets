"""Copia la base de PRODUCCIÓN a la base de STAGING (Railway).

Producción solo se LEE (dumpdata). La base de staging se vacía y se recarga completa.

Uso (desde C:\\dev\\hoteltickets):
    .\\venv\\Scripts\\python.exe scripts\\copy_prod_to_staging.py
"""
import datetime
import os
import subprocess
import sys

from pull_prod_db import BASE, LOCAL, prod_url

DUMP_ARGS = ['dumpdata', '--natural-foreign', '--natural-primary',
             '-e', 'contenttypes', '-e', 'auth.permission',
             '-e', 'sessions', '-e', 'admin.logentry', '--indent', '1']


def run(args, url, **kw):
    env = {**os.environ, 'DATABASE_URL': url}
    return subprocess.run([sys.executable, '-X', 'utf8', 'manage.py', *args], cwd=BASE, env=env, check=True, **kw)


def main():
    prod, staging = prod_url('production'), prod_url('staging')
    if prod == staging:
        sys.exit('ERROR: staging apunta a la misma base que producción. No se copia nada.')
    if input('Esto REEMPLAZA todos los datos de STAGING. Escribe STAGING para continuar: ').strip() != 'STAGING':
        sys.exit('Cancelado.')

    LOCAL.mkdir(exist_ok=True)
    dump = LOCAL / f'prod-{datetime.datetime.now():%Y%m%d-%H%M%S}.json'
    print('1/4 Leyendo producción...')
    with open(dump, 'w', encoding='utf-8') as fh:
        run(DUMP_ARGS, prod, stdout=fh)
    print('2/4 Migrando staging...')
    run(['migrate', '--no-input'], staging)
    print('3/4 Vaciando staging...')
    run(['flush', '--no-input'], staging)
    print('4/4 Cargando datos en staging...')
    run(['loaddata', str(dump)], staging)
    print(f'Listo. Staging = copia de producción ({dump.name})')


if __name__ == '__main__':
    main()
