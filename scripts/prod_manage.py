"""Corre un comando de manage.py contra la base de PRODUCCIÓN (o STAGING) en Railway.

¡Cuidado! Lo que escriba este comando cambia los datos de ese ambiente.

Uso (desde C:\\dev\\hoteltickets):
    .\\venv\\Scripts\\python.exe scripts\\prod_manage.py createsuperuser
    .\\venv\\Scripts\\python.exe scripts\\prod_manage.py changepassword <usuario>
    .\\venv\\Scripts\\python.exe scripts\\prod_manage.py --staging migrate
"""
import os
import subprocess
import sys

from pull_prod_db import BASE, prod_url


def main():
    args = sys.argv[1:]
    environment = 'production'
    if args and args[0] == '--staging':
        environment, args = 'staging', args[1:]
    if not args:
        sys.exit(__doc__)
    palabra = 'PROD' if environment == 'production' else 'STAGING'
    print(f'Vas a correr contra {environment.upper()}: manage.py {" ".join(args)}')
    if input(f'Escribe {palabra} para continuar: ').strip() != palabra:
        sys.exit('Cancelado.')
    env = {**os.environ, 'DATABASE_URL': prod_url(environment)}
    sys.exit(subprocess.run([sys.executable, 'manage.py', *args], cwd=BASE, env=env).returncode)


if __name__ == '__main__':
    main()
