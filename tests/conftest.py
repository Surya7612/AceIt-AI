import sys
from pathlib import Path

import pytest

# Pytest does not put the repo root on sys.path by default; ``extensions`` lives at project root.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# OpenAI SDK refuses to construct a client with no api_key; tests never need a real key at import time.
import os

os.environ.setdefault(
    "OPENAI_API_KEY",
    "sk-test-pytest-placeholder-not-for-real-api-calls",
)
# ``extensions`` calls ``db.init_app`` at import time; Flask-SQLAlchemy requires a URI.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
# Avoid live embedding API calls during collection unless a test opts in.
os.environ.setdefault("RAG_USE_EMBEDDINGS", "false")
os.environ.setdefault("RAG_QUERY_EXPAND", "false")
os.environ.setdefault("RAG_LLM_RERANK", "false")

from extensions import app as flask_app, db

# Side effects: registers routes, blueprints (including `/health`), and template filters on ``flask_app``.
import app as _app_routes  # noqa: F401, PLC0415


@pytest.fixture
def app():
    flask_app.config["TESTING"] = True
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    flask_app.config["WTF_CSRF_ENABLED"] = False

    with flask_app.app_context():
        import models  # noqa: F401, PLC0415

        db.create_all()
        yield flask_app
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
