   release: python manage.py migrate --no-input && python manage.py collectstatic --no-input
   web: python manage.py collectstatic --no-input && gunicorn config.wsgi --log-file -
