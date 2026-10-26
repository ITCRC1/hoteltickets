"""Corre un comando de manage.py contra la base de PRODUCCIÓN (Railway).

¡Cuidado! Lo que escriba este comando cambia los datos reales.

Uso (desde C:\\dev\\hoteltickets):
    .\\venv\\Scripts\\python.exe scripts\\prod_manage.py createsuperuser
    .\\venv\\Scripts\\python.exe scripts\\prod_manage.py changepassword <usuario>
"""
import os
import subprocess
import sys

from pull_prod_db import BASE, prod_url


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    args = sys.argv[1:]
    print(f'Vas a correr contra PRODUCCIÓN: manage.py {" ".join(args)}')
    if input('Escribe PROD para continuar: ').strip() != 'PROD':
        sys.exit('Cancelado.')
    env = {**os.environ, 'DATABASE_URL': prod_url()}
    sys.exit(subprocess.run([sys.executable, 'manage.py', *args], cwd=BASE, env=env).returncode)


if __name__ == '__main__':
    main()
