import os
import logging
from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.utils import secure_filename

from ai_helper import generate_study_plan, chat_response
from ocr_helper import extract_text_from_image

# Setup logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app = Flask(__name__)

# Configuration
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev_key_replace_in_production")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///study_assistant.db")
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

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Extract text from image if it's an image file
        if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            extracted_text = extract_text_from_image(filepath)
            if extracted_text:
                return jsonify({
                    'success': True,
                    'text': extracted_text,
                    'filename': filename
                })

        return jsonify({
            'success': True,
            'filename': filename
        })

    return jsonify({'error': 'File type not allowed'}), 400

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

@app.route('/generate-plan', methods=['POST'])
def generate_plan():
    data = request.get_json()
    if not data or not all(k in data for k in ('topic', 'duration', 'goals')):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        study_plan = generate_study_plan(
            f"Topic: {data['topic']}\nDuration: {data['duration']} hours\nGoals: {data['goals']}"
        )
        return jsonify({'plan': study_plan})
    except Exception as e:
        logging.error(f"Study plan generation error: {str(e)}")
        return jsonify({'error': 'Failed to generate study plan'}), 500

with app.app_context():
    db.create_all()