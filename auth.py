from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from models import User, db
from email_validator import validate_email, EmailNotValidError
import re

auth = Blueprint('auth', __name__)

def validate_password(password):
    """
    Validate password complexity requirements:
    - At least 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one number
    - At least one special character
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"

    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"

    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r"\d", password):
        return False, "Password must contain at least one number"

    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must contain at least one special character"

    return True, None

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))

        flash('Please check your login details and try again.')
        return redirect(url_for('auth.login'))

    return render_template('auth/login.html')

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')

        try:
            # Validate email
            validate_email(email)
        except EmailNotValidError:
            flash('Invalid email address.')
            return redirect(url_for('auth.register'))

        # Check if email already exists
        if User.query.filter_by(email=email).first():
            flash('Email already exists.')
            return redirect(url_for('auth.register'))

        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists.')
            return redirect(url_for('auth.register'))

        # Validate password complexity
        is_valid, error_message = validate_password(password)
        if not is_valid:
            flash(error_message)
            return redirect(url_for('auth.register'))

        # Create new user
        new_user = User(
            email=email,
            username=username,
            is_admin=False  # Default to non-admin
        )
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        # Auto-login after registration
        login_user(new_user)
        return redirect(url_for('index'))

    return render_template('auth/register.html')

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# Admin route for managing users
@auth.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin:
        flash('Access denied.')
        return redirect(url_for('index'))

    users = User.query.all()
    return render_template('auth/admin_users.html', users=users)