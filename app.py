import os
import logging
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, url_for
from werkzeug.utils import secure_filename
from extensions import db
from ai_helper import chat_response, generate_study_schedule, update_study_plan
from ocr_helper import extract_text_from_image
from document_processor import DocumentProcessor
import openai # Added import for OpenAI

# Setup logging
logging.basicConfig(level=logging.DEBUG)

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
            from models import StudyPlan, Document
            # Handle form data
            topic = request.form.get('topic')
            priority = request.form.get('priority')
            daily_time = request.form.get('daily_time')
            completion_date = request.form.get('completion_date')
            difficulty = request.form.get('difficulty')
            goals = request.form.get('goals')

            if not all([topic, priority, daily_time, completion_date, difficulty, goals]):
                return jsonify({'error': 'Missing required fields'}), 400

            documents = []

            # Handle file uploads
            uploaded_files = request.files.getlist('files')
            for file in uploaded_files:
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)

                    file_type = 'image' if filename.lower().endswith(('.png', '.jpg', '.jpeg')) else 'pdf'
                    doc = Document(
                        filename=filename,
                        original_filename=file.filename,
                        file_type=file_type,
                        processed=False,
                        user_id=1  # Default user
                    )
                    db.session.add(doc)
                    documents.append(doc)

            # Handle URL
            link = request.form.get('link')
            if link:
                doc = Document(
                    filename=link,
                    original_filename=link,
                    file_type='link',
                    content=link,
                    processed=False,
                    user_id=1
                )
                db.session.add(doc)
                documents.append(doc)

            # If no materials provided, generate AI content
            if not documents:
                logging.info(f"No materials provided, generating AI content for topic: {topic}")
                # Generate AI study material
                ai_content = openai.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "system",
                            "content": """Create comprehensive study material for the given topic.
                            Include detailed explanations, examples, practice problems, and key concepts.
                            Structure the content in a clear, organized manner."""
                        },
                        {
                            "role": "user",
                            "content": f"Create study material for: {topic}\nDifficulty: {difficulty}\nGoals: {goals}"
                        }
                    ],
                    response_format={"type": "json_object"}
                )

                # Create a document with AI-generated content
                doc = Document(
                    filename=f"ai_generated_{topic.lower().replace(' ', '_')}.txt",
                    original_filename=f"AI Generated Content - {topic}",
                    file_type='text',
                    content=ai_content.choices[0].message.content,
                    processed=True,
                    category='General',  # Will be updated by AI processing
                    user_id=1
                )
                db.session.add(doc)
                documents.append(doc)

            db.session.flush()  # Get IDs for the documents

            # Start processing documents in background
            from celery_worker import process_document_task
            for doc in documents:
                if not doc.processed:
                    process_document_task.delay(doc.id)

            # Generate optimized study schedule
            schedule = generate_study_schedule(
                topic=topic,
                priority=int(priority),
                daily_time=int(daily_time),
                completion_date=completion_date,
                difficulty=difficulty,
                goals=goals
            )

            # Create study plan
            study_plan = StudyPlan(
                title=topic,
                category='General',  # Will be updated based on documents
                content=json.dumps(schedule),
                user_id=1,  # Default user
                priority=int(priority),
                daily_study_time=int(daily_time),
                difficulty_level=difficulty,
                completion_target=datetime.strptime(completion_date, '%Y-%m-%d'),
                schedule=json.dumps(schedule.get('daily_sessions', [])),
                progress=0
            )

            # Associate documents with study plan
            study_plan.documents.extend(documents)

            db.session.add(study_plan)
            db.session.commit()

            return jsonify({'success': True, 'plan': schedule})
        except Exception as e:
            logging.error(f"Study plan creation error: {str(e)}")
            return jsonify({'error': str(e)}), 500

    plans = StudyPlan.query.order_by(StudyPlan.created_at.desc()).all()
    return render_template('study_plan.html', plans=plans)

@app.route('/study-plan/<int:plan_id>/session/start', methods=['POST'])
def start_study_session(plan_id):
    try:
        from models import StudyPlan, StudySession
        study_plan = StudyPlan.query.get_or_404(plan_id)

        # Create new study session
        session = StudySession(study_plan_id=plan_id)
        db.session.add(session)
        db.session.commit()

        return jsonify({
            'success': True,
            'session_id': session.id,
            'start_time': session.start_time.isoformat()
        })
    except Exception as e:
        logging.error(f"Error starting study session: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/study-plan/<int:plan_id>/session/<int:session_id>/end', methods=['POST'])
def end_study_session(plan_id, session_id):
    try:
        from models import StudySession
        session = StudySession.query.get_or_404(session_id)

        # Verify session belongs to the correct plan
        if session.study_plan_id != plan_id:
            return jsonify({'error': 'Invalid session ID'}), 400

        notes = request.json.get('notes', '')
        session.complete_session(notes)
        db.session.commit()

        return jsonify({
            'success': True,
            'duration_minutes': session.duration_minutes,
            'total_study_time': session.study_plan.total_study_time,
            'progress': session.study_plan.progress
        })
    except Exception as e:
        logging.error(f"Error ending study session: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Initialize document processor
doc_processor = DocumentProcessor()

# Update document upload endpoint to use background processing
@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        from models import Document
        from celery_worker import process_document_task

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
            db.session.commit()

            # Start background processing
            process_document_task.delay(doc.id)

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

                file_type = 'image' if filename.lower().endswith(('.png', '.jpg', '.jpeg')) else 'pdf'

                doc = Document(
                    filename=filename,
                    original_filename=file.filename,
                    file_type=file_type,
                    processed=False,
                    user_id=1  # Temporary default user ID
                )
                db.session.add(doc)
                db.session.commit()

                # Start background processing
                process_document_task.delay(doc.id)

                results.append({
                    'type': 'file',
                    'filename': filename,
                    'success': True
                })

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
    from models import Document, StudyPlan
    # Get user's documents and study plans for context
    documents = Document.query.filter_by(user_id=1, processed=True).all()
    study_plans = StudyPlan.query.filter_by(user_id=1).all()
    return render_template('chat.html', documents=documents, study_plans=study_plans)

@app.route('/chat', methods=['POST'])
def process_chat():
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({'error': 'No message provided'}), 400

    try:
        tutor_mode = data.get('tutor_mode', False)
        response = chat_response(data['message'], tutor_mode=tutor_mode)
        return jsonify({'response': response})
    except Exception as e:
        logging.error(f"Chat error: {str(e)}")
        return jsonify({'error': 'Failed to generate response'}), 500

@app.route('/study-plan/<int:plan_id>')
def view_study_plan(plan_id):
    from models import StudyPlan
    study_plan = StudyPlan.query.get_or_404(plan_id)
    return render_template('study_plan_view.html', study_plan=study_plan)

@app.route('/documents/combine', methods=['POST'])
def combine_documents():
    try:
        data = request.get_json()
        if not data or 'document_ids' not in data:
            return jsonify({'error': 'No documents selected'}), 400

        from models import Document, StudyPlan
        from celery_worker import combine_documents_task

        # Get selected documents
        documents = Document.query.filter(Document.id.in_(data['document_ids'])).all()
        if len(documents) < 2:
            return jsonify({'error': 'Please select at least 2 documents'}), 400

        # Start background task for combining documents
        task = combine_documents_task.delay(data['document_ids'], 1)  # user_id=1
        combined_content = task.get(timeout=30)  # Wait for result with timeout

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
            'redirect_url': url_for('view_study_plan', plan_id=study_plan.id)
        })

    except Exception as e:
        logging.error(f"Error combining documents: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/study-plan/<int:plan_id>/update', methods=['POST'])
def update_study_plan_schedule(plan_id):
    try:
        data = request.get_json()
        if not data or 'updates' not in data:
            return jsonify({'error': 'No updates provided'}), 400

        if update_study_plan(plan_id, data['updates']):
            return jsonify({'success': True})
        return jsonify({'error': 'Failed to update study plan'}), 500

    except Exception as e:
        logging.error(f"Error updating study plan: {str(e)}")
        return jsonify({'error': str(e)}), 500

with app.app_context():
    # Import models here to avoid circular imports
    import models
    db.create_all()