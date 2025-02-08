from extensions import app, db
from models import User

def create_admin_user():
    with app.app_context():
        # Check if admin already exists
        admin = User.query.filter_by(email='admin@aceit.ai').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@aceit.ai',
                is_admin=True
            )
            admin.set_password('admin123')  # Set a secure password in production
            db.session.add(admin)
            db.session.commit()
            print("Admin user created successfully")
        else:
            print("Admin user already exists")

if __name__ == '__main__':
    create_admin_user()
