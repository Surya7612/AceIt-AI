import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_login import LoginManager
from openai import OpenAI
from flask_wtf.csrf import CSRFProtect

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

# Initialize extensions
db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()
csrf = CSRFProtect()

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Create Flask app
app = Flask(__name__)

# Configure Flask app
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev_key")
app.config.update(
    # Database settings
    SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL"),
    SQLALCHEMY_ENGINE_OPTIONS={
        "pool_recycle": 300,
        "pool_pre_ping": True,
    },
    # Upload settings
    UPLOAD_FOLDER='uploads',
    # Security settings
    WTF_CSRF_ENABLED=True,
    WTF_CSRF_SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "dev_key"),
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    PERMANENT_SESSION_LIFETIME=1800  # 30 minutes
)

# Initialize extensions with app
db.init_app(app)
csrf.init_app(app)  # Initialize CSRF after app configuration
login_manager.init_app(app)

# Configure login
login_manager.login_view = 'auth.login'

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def handle_csrf_error(e):
    logger.error(f"CSRF Error: {e.description}")
    return "CSRF token validation failed", 400

app.register_error_handler(400, handle_csrf_error)

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))