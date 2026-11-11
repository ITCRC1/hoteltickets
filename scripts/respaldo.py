"""Respaldo de la base de PRODUCCIÓN (o STAGING) en Railway, de solo lectura.

Lee TODAS las tablas directamente con SQL (sesión de solo lectura), sin depender de los modelos del código:
funciona aunque el código local tenga tablas o columnas que producción todavía no tiene (justo el caso de
antes de cada paso a producción). Guarda un JSON por respaldo en .local/respaldos/ (excluido de git).

Uso (desde C:\\dev\\hoteltickets):
    .\\venv\\Scripts\\python.exe scripts\\respaldo.py              # producción
    .\\venv\\Scripts\\python.exe scripts\\respaldo.py --staging    # staging
"""
import datetime
import decimal
import json
import sys
import uuid
from urllib.parse import parse_qs, urlparse

import psycopg2

from pull_prod_db import BASE, prod_url


def _json(v):
    if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return str(v)
    if isinstance(v, (uuid.UUID, memoryview, bytes)):
        return str(v) if not isinstance(v, (memoryview, bytes)) else bytes(v).hex()
    raise TypeError(type(v))


def conectar(url):
    u = urlparse(url)
    extra = {k: v[0] for k, v in parse_qs(u.query).items()}  # p. ej. hostaddr cuando el DNS local falla
    con = psycopg2.connect(host=u.hostname, port=u.port, user=u.username, password=u.password,
                           dbname=u.path.lstrip('/'), connect_timeout=15, **extra)
    con.set_session(readonly=True)
    return con


def main():
    ambiente = 'staging' if '--staging' in sys.argv else 'production'
    con = conectar(prod_url(ambiente))
    cur = con.cursor()
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
    tablas = [t for (t,) in cur.fetchall()]
    datos, conteo = {}, {}
    for t in tablas:
        cur.execute(f'SELECT * FROM "{t}"')
        columnas = [d[0] for d in cur.description]
        filas = cur.fetchall()
        datos[t] = {'columnas': columnas, 'filas': filas}
        conteo[t] = len(filas)
    cur.execute('SELECT app, name FROM django_migrations ORDER BY id')
    migraciones = [f'{a}.{n}' for a, n in cur.fetchall()]
    con.close()

    destino = BASE / '.local' / 'respaldos'
    destino.mkdir(parents=True, exist_ok=True)
    archivo = destino / f'{ambiente}-{datetime.datetime.now():%Y%m%d-%H%M%S}.json'
    archivo.write_text(json.dumps({'ambiente': ambiente, 'creado': datetime.datetime.now().isoformat(),
                                   'migraciones': migraciones, 'tablas': datos}, default=_json, ensure_ascii=False),
                       encoding='utf-8')
    importantes = {k: v for k, v in conteo.items() if k.startswith(('tickets_', 'core_', 'tareas_', 'inventario_',
                                                                     'finanzas_', 'auth_user'))}
    print(f'Respaldo de {ambiente}: {archivo}')
    print(f'{len(tablas)} tablas · {sum(conteo.values())} filas · última migración: {migraciones[-1] if migraciones else "—"}')
    for t, n in sorted(importantes.items()):
        print(f'  {t}: {n}')


if __name__ == '__main__':
    main()
