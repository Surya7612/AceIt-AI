# AceIt AI - Agent Instructions

## Cursor Cloud specific instructions

**Product**: AceIt AI — Flask-based interview preparation platform with AI (OpenAI GPT-4) integration, PostgreSQL database, Redis caching, and Celery background tasks.

### Services

| Service | Command | Port |
|---------|---------|------|
| PostgreSQL | `sudo pg_ctlcluster 16 main start` | 5432 |
| Redis | `redis-server --port 6379 --save "" --dir /tmp --daemonize yes` | 6379 |
| Flask (dev) | `uv run python main.py` | 5000 |
| Celery (optional) | `uv run celery -A celery_worker worker --loglevel=info` | N/A |

### Required environment variables

```
DATABASE_URL=postgresql://aceit:aceit_dev_pass@localhost:5432/aceit_db
FLASK_SECRET_KEY=dev_secret_key_for_testing_12345
OPENAI_API_KEY=<real-key-or-placeholder>
REDIS_URL=redis://127.0.0.1:6379/0
```

### Gotchas

- **Redis RDB file**: If a stale `dump.rdb` exists in the working directory, Redis may fail to start with "Can't handle RDB format version" error. Delete it and start Redis with `--dir /tmp --save ""` to avoid persistence issues.
- **CSRF on registration**: The register form template (`templates/auth/register.html`) is missing a `{{ csrf_token() }}` hidden field, so browser-based registration will fail with "CSRF token validation failed". The login form (`templates/auth/login.html`) includes it and works correctly. As a workaround, create users programmatically via the Python shell.
- **SESSION_COOKIE_SECURE**: Set to `True` in `extensions.py`. On localhost over HTTP, modern Chrome still sends Secure cookies for localhost, so login works in the browser. Other HTTP clients (e.g., curl) may have issues.
- **No test suite or linters**: The project has no pytest, flake8, ruff, or other testing/linting configuration. Code correctness can be verified with `python -m py_compile <file>`.
- **`uv` is the package manager**: Dependencies are managed via `pyproject.toml` + `uv.lock`. Use `uv sync` to install and `uv run` to execute commands in the virtual environment.
- **Database initialization**: Tables are auto-created via `db.create_all()` when the app starts (in `app.py`). No Flask-Migrate or Alembic is configured.
- **OpenAI API**: Most AI features (study plans, interview questions, chat) require a valid `OPENAI_API_KEY`. The app starts and serves pages without one, but AI-powered endpoints will return errors.
