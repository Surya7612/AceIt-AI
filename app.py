import os
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

from ai_helper import generate_study_plan, chat_response
from ocr_helper import extract_text_from_image

# Setup logging
logging.basicConfig(level=logging.DEBUG)

db = SQLAlchemy()
app = Flask(__name__)

# Configuration
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "a secret key"
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max file size

# Initialize extensions
db.init_app(app)

# Ensure upload directory exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat')
def chat():
    return render_template('chat.html')

@app.route('/study-plan')
def study_plan():
    return render_template('study_plan.html')

@app.route('/study-plan/new', methods=['GET', 'POST'])
def create_study_plan():
    if request.method == 'POST':
        try:
            data = request.get_json()
            if not data or not all(k in data for k in ('topic', 'duration', 'goals')):
                return jsonify({'error': 'Missing required fields'}), 400

            # For now, we'll store study plans without user association
            # This is temporary until user authentication is implemented
            from models import StudyPlan
            study_plan = StudyPlan(
                title=data['topic'],
                category='General',
                content=generate_study_plan(
                    f"Topic: {data['topic']}\nDuration: {data['duration']} hours\nGoals: {data['goals']}"
                ),
                user_id=1,  # Temporary default user ID
                completion_target=datetime.utcnow() + timedelta(hours=int(data['duration']))
            )
            db.session.add(study_plan)
            db.session.commit()

            return jsonify({'success': True, 'plan': study_plan.content})
        except Exception as e:
            logging.error(f"Study plan creation error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    return render_template('study_plan.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        from models import Document

        # Debug logging
        logging.debug(f"Files in request: {request.files}")
        logging.debug(f"Form data: {request.form}")

        uploaded_files = request.files.getlist('files')
        link = request.form.get('link')
        results = []

        # Handle link if provided
        if link:
            doc = Document(
                filename=link,
                original_filename=link,
                file_type='link',
                content=link,
                processed=True,
                user_id=1  # Temporary default user ID
            )
            db.session.add(doc)
            results.append({
                'type': 'link',
                'filename': link,
                'success': True
            })

        # Handle uploaded files
        for file in uploaded_files:
            logging.debug(f"Processing file: {file.filename}")
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)

                content = None
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    content = extract_text_from_image(filepath)

                doc = Document(
                    filename=filename,
                    original_filename=file.filename,
                    file_type=filename.rsplit('.', 1)[1].lower(),
                    content=content,
                    processed=bool(content),
                    user_id=1  # Temporary default user ID
                )
                db.session.add(doc)
                results.append({
                    'type': 'file',
                    'filename': filename,
                    'success': True,
                    'text': content if content else None
                })

        db.session.commit()
        return jsonify({'success': True, 'results': results})

    except Exception as e:
        logging.error(f"Upload error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/chat', methods=['POST'])
def process_chat():
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({'error': 'No message provided'}), 400

    try:
        response = chat_response(data['message'])
        return jsonify({'response': response})
    except Exception as e:
        logging.error(f"Chat error: {str(e)}")
        return jsonify({'error': 'Failed to generate response'}), 500

with app.app_context():
    # Import models here to avoid circular imports
    import models
    db.create_all()