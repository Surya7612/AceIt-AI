import os
import logging
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from ai_helper import generate_study_plan, chat_response
from ocr_helper import extract_text_from_image
from document_processor import DocumentProcessor

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

# Custom Jinja2 filters
@app.template_filter('parse_json')
def parse_json_filter(value):
    try:
        return json.loads(value) if value else None
    except:
        return None

# Ensure upload directory exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    from models import Document, StudyPlan
    recent_docs = Document.query.order_by(Document.created_at.desc()).limit(5).all()
    recent_plans = StudyPlan.query.order_by(StudyPlan.created_at.desc()).limit(5).all()
    return render_template('index.html', recent_docs=recent_docs, recent_plans=recent_plans)

@app.route('/documents')
def documents():
    from models import Document
    documents = Document.query.order_by(Document.created_at.desc()).all()
    return render_template('documents.html', documents=documents)

@app.route('/study-plan')
def study_plan():
    from models import StudyPlan
    plans = StudyPlan.query.order_by(StudyPlan.created_at.desc()).all()
    return render_template('study_plan.html', plans=plans)

@app.route('/study-plan/new', methods=['GET', 'POST'])
def create_study_plan():
    if request.method == 'POST':
        try:
            data = request.get_json()
            if not data or not all(k in data for k in ('topic', 'duration', 'goals')):
                return jsonify({'error': 'Missing required fields'}), 400

            from models import StudyPlan
            content = generate_study_plan(
                f"Topic: {data['topic']}\nDuration: {data['duration']} hours\nGoals: {data['goals']}"
            )

            # Create study plan
            study_plan = StudyPlan(
                title=data['topic'],
                category='General',
                content=content,
                user_id=1,  # Default user
                completion_target=datetime.utcnow() + timedelta(hours=int(data['duration']))
            )

            db.session.add(study_plan)
            db.session.commit()

            return jsonify({'success': True, 'plan': content})
        except Exception as e:
            logging.error(f"Study plan creation error: {str(e)}")
            return jsonify({'error': str(e)}), 500

    return render_template('study_plan.html')

# Initialize document processor
doc_processor = DocumentProcessor()

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
                processed=False,
                user_id=1  # Temporary default user ID
            )
            db.session.add(doc)

            # Process link content
            structured_content = doc_processor.process_document('link', link)
            if structured_content:
                doc.structured_content = structured_content
                doc.processed = True

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

                # Determine file type and process content
                file_type = 'image' if filename.lower().endswith(('.png', '.jpg', '.jpeg')) else 'pdf'
                content = None
                structured_content = None

                if file_type == 'image':
                    content = extract_text_from_image(filepath)
                    if content:
                        structured_content = doc_processor.process_document('image', filepath)

                doc = Document(
                    filename=filename,
                    original_filename=file.filename,
                    file_type=file_type,
                    content=content,
                    structured_content=structured_content,
                    processed=bool(structured_content),
                    user_id=1  # Temporary default user ID
                )
                db.session.add(doc)
                results.append({
                    'type': 'file',
                    'filename': filename,
                    'success': True,
                    'processed': bool(structured_content)
                })

        db.session.commit()
        return jsonify({'success': True, 'results': results})

    except Exception as e:
        logging.error(f"Upload error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/document/<int:doc_id>')
def view_document(doc_id):
    from models import Document
    document = Document.query.get_or_404(doc_id)
    return render_template('document_view.html', document=document, content=document.structured_content)

@app.route('/chat')
def chat():
    return render_template('chat.html')

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

@app.route('/documents/combine', methods=['POST'])
def combine_documents():
    try:
        data = request.get_json()
        if not data or 'document_ids' not in data:
            return jsonify({'error': 'No documents selected'}), 400

        from models import Document, StudyPlan

        # Get selected documents
        documents = Document.query.filter(Document.id.in_(data['document_ids'])).all()
        if len(documents) < 2:
            return jsonify({'error': 'Please select at least 2 documents'}), 400

        # Combine documents using document processor
        combined_content = doc_processor.combine_documents(documents)

        # Create a new study plan from combined content
        study_plan = StudyPlan(
            title=f"Combined Study Plan: {combined_content['title']}",
            category='Combined',
            content=json.dumps(combined_content),
            user_id=1,  # Default user
            completion_target=datetime.utcnow() + timedelta(days=7)  # Default 1 week
        )

        db.session.add(study_plan)
        db.session.commit()

        return jsonify({
            'success': True,
            'redirect_url': url_for('view_document', doc_id=study_plan.id)
        })

    except Exception as e:
        logging.error(f"Error combining documents: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

with app.app_context():
    # Import models here to avoid circular imports
    import models
    db.create_all()