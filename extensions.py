import os
import logging
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_login import LoginManager
from flask_migrate import Migrate
from openai import OpenAI
from flask_wtf.csrf import CSRFProtect, CSRFError

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def normalize_database_url(url: str | None) -> str | None:
    """Railway/Heroku sometimes expose ``postgres://``; SQLAlchemy expects ``postgresql://``."""
    if url and url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


class Base(DeclarativeBase):
    pass

# Initialize extensions
db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Create Flask app
app = Flask(__name__)

# Configure Flask app
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev_key")
app.config.update(
    # Database settings
    SQLALCHEMY_DATABASE_URI=normalize_database_url(os.environ.get("DATABASE_URL")),
    SQLALCHEMY_ENGINE_OPTIONS={
        "pool_recycle": 300,
        "pool_pre_ping": True,
    },
    # Upload settings
    UPLOAD_FOLDER='uploads',
    # Security settings
    WTF_CSRF_ENABLED=True,
    WTF_CSRF_SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "dev_key"),
    # Set SESSION_COOKIE_SECURE=true in production (HTTPS); default off for local http:// dev
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower()
    in ("1", "true", "yes"),
    SESSION_COOKIE_HTTPONLY=True,
    PERMANENT_SESSION_LIFETIME=1800  # 30 minutes
)

# Initialize extensions with app
db.init_app(app)
migrate.init_app(app, db)
csrf.init_app(app)  # Initialize CSRF after app configuration
login_manager.init_app(app)

# Configure login
login_manager.login_view = 'auth.login'

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    logger.warning("CSRF validation failed: %s", e.description)
    if (
        request.path.startswith("/webhook")
        or request.accept_mimetypes.best == "application/json"
        or request.content_type == "application/json"
    ):
        return jsonify(error="CSRF token validation failed"), 400
    return "CSRF token validation failed", 400

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))