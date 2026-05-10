release: FLASK_APP=main:app flask db upgrade
web: gunicorn "app:app" --bind "0.0.0.0:${PORT:-5000}" --access-logfile - --error-logfile - --log-level debug
worker: celery -A celery_worker worker --loglevel=info