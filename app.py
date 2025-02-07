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
import openai
from openai import OpenAI
import random # Added for confidence score generation

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
            # Get form data
            topic = request.form.get('topic')
            priority = request.form.get('priority')
            daily_time = request.form.get('daily_time')
            completion_date = request.form.get('completion_date')
            difficulty = request.form.get('difficulty')
            goals = request.form.get('goals')

            logging.info(f"Received form data: topic={topic}, priority={priority}, daily_time={daily_time}, "
                        f"completion_date={completion_date}, difficulty={difficulty}, goals={goals}")

            if not all([topic, priority, daily_time, completion_date, difficulty, goals]):
                return jsonify({'error': 'Missing required fields'}), 400

            documents = []

            # If no materials provided, generate AI content
            if not documents:
                logging.info(f"No materials provided, generating AI content for topic: {topic}")
                try:
                    client = OpenAI()

                    # Enhanced error handling for OpenAI client
                    if not os.environ.get("OPENAI_API_KEY"):
                        raise ValueError("OpenAI API key is not set")

                    # Generate AI study material with enhanced prompt
                    content_prompt = f"""Create a comprehensive study plan and materials for:
Topic: {topic}
Learning Objectives: {goals}
Priority Level: {priority} (1=High, 2=Medium, 3=Low)
Daily Study Time: {daily_time} minutes
Target Completion Date: {completion_date}
Difficulty Level: {difficulty}

Ensure the study plan:
1. Fits within the daily time commitment of {daily_time} minutes
2. Prioritizes content based on the priority level {priority}
3. Structures content to meet the target completion date
4. Adapts complexity to match the {difficulty} difficulty level

Focus on addressing the specific learning objectives while covering the topic thoroughly."""

                    logging.info("Sending request to OpenAI with prompt")
                    ai_content = client.chat.completions.create(
                        model="gpt-4",  # Fixed model name
                        messages=[
                            {
                                "role": "system",
                                "content": """You are a study plan generator that creates detailed, structured content.
Always respond with valid JSON following this structure:
{
    "title": "Study Topic",
    "difficulty_level": "beginner|intermediate|advanced",
    "estimated_study_time": "number",
    "summary": "Brief overview focusing on learning objectives",
    "key_concepts": [
        {
            "name": "Concept name",
            "description": "Detailed explanation",
            "priority": "high|medium|low"
        }
    ],
    "sections": [
        {
            "heading": "Section title",
            "content": "Detailed content",
            "key_points": ["point 1", "point 2"],
            "examples": ["example 1", "example 2"],
            "time_allocation": "number",
            "priority": "high|medium|low"
        }
    ],
    "practice_questions": [
        {
            "question": "Question text",
            "answer": "Answer text",
            "explanation": "Detailed explanation",
            "difficulty": "easy|medium|hard"
        }
    ]
}"""
                            },
                            {
                                "role": "user",
                                "content": content_prompt
                            }
                        ]
                    )

                    content = ai_content.choices[0].message.content
                    logging.info(f"Generated AI content: {content[:200]}...")  # Log first 200 chars

                    # Verify JSON structure
                    try:
                        parsed_content = json.loads(content)
                        if not isinstance(parsed_content, dict):
                            raise ValueError("Generated content is not a valid JSON object")
                    except json.JSONDecodeError as e:
                        logging.error(f"Invalid JSON content: {str(e)}")
                        return jsonify({'error': 'Failed to generate valid study plan content'}), 500

                    # Create study plan with verified content
                    study_plan = StudyPlan(
                        title=topic,
                        category='General',
                        content=content,  # Use the raw AI-generated content
                        user_id=1,
                        priority=int(priority),
                        daily_study_time=int(daily_time),
                        difficulty_level=difficulty,
                        completion_target=datetime.strptime(completion_date, '%Y-%m-%d'),
                        schedule=json.dumps(parsed_content.get('sections', [])),
                        progress=0
                    )

                    # Associate documents with study plan
                    study_plan.documents.extend(documents)

                    db.session.add(study_plan)
                    db.session.commit()
                    logging.info("Successfully created study plan")

                    return jsonify({'success': True, 'plan': parsed_content})

                except Exception as e:
                    logging.error(f"Error in AI content generation: {str(e)}", exc_info=True)
                    return jsonify({'error': f'Failed to generate study plan: {str(e)}'}), 500

        except Exception as e:
            logging.error(f"Study plan creation error: {str(e)}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    plans = StudyPlan.query.order_by(StudyPlan.created_at.desc()).all()
    return render_template('study_plan_new.html', plans=plans)

@app.route('/study-plan/<int:plan_id>/delete', methods=['POST'])
def delete_study_plan(plan_id):
    """Delete a study plan"""
    try:
        from models import StudyPlan
        study_plan = StudyPlan.query.get_or_404(plan_id)
        db.session.delete(study_plan)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"Error deleting study plan: {str(e)}")
        return jsonify({'error': str(e)}), 500

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
    try:
        from models import Document, StudyPlan, ChatHistory
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'No message provided'}), 400

        # Get user's processed documents and study plans for context
        documents = Document.query.filter_by(user_id=1, processed=True).all()
        study_plans = StudyPlan.query.filter_by(user_id=1).all()

        # Build context from documents and study plans
        context = "Consider this context from the user's materials:\n\n"

        # Add document contexts
        for doc in documents:
            context += f"From document '{doc.original_filename}':\n{doc.content}\n\n"

        # Add study plan contexts
        for plan in study_plans:
            context += f"From study_plan '{plan.title}':\n{plan.content}\n\n"

        tutor_mode = data.get('tutor_mode', False)

        try:
            response = chat_response(
                data['message'],
                context=context,
                tutor_mode=tutor_mode
            )

            # Store chat history
            chat_history = ChatHistory(
                user_id=1,
                question=data['message'],
                answer=response
            )
            db.session.add(chat_history)
            db.session.commit()

            return jsonify({'response': response})
        except Exception as e:
            logging.error(f"Chat generation error: {str(e)}")
            return jsonify({'error': 'Failed to generate response'}), 500

    except Exception as e:
        logging.error(f"Chat error: {str(e)}")
        return jsonify({'error': str(e)}), 500

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


# Add these new routes after the existing routes
@app.route('/folders', methods=['GET', 'POST'])
def folders():
    if request.method == 'POST':
        try:
            from models import Folder
            name = request.json.get('name')
            parent_id = request.json.get('parent_id')

            if not name:
                return jsonify({'error': 'Folder name is required'}), 400

            folder = Folder(
                name=name,
                parent_id=parent_id,
                user_id=1  # Default user
            )
            db.session.add(folder)
            db.session.commit()

            return jsonify({
                'success': True,
                'folder': {
                    'id': folder.id,
                    'name': folder.name,
                    'parent_id': folder.parent_id
                }
            })
        except Exception as e:
            logging.error(f"Error creating folder: {str(e)}")
            return jsonify({'error': str(e)}), 500

    from models import Folder, StudyPlan, Document
    folders = Folder.query.filter_by(user_id=1).all()
    study_plans = StudyPlan.query.filter_by(user_id=1).all()
    documents = Document.query.filter_by(user_id=1).all()
    return render_template('folders.html', folders=folders, study_plans=study_plans, documents=documents)

@app.route('/folders/<int:folder_id>/items', methods=['POST'])
def update_folder_items(folder_id):
    try:
        from models import Folder, StudyPlan, Document
        data = request.get_json()
        item_type = data.get('type')
        item_id = data.get('id')

        folder = Folder.query.get_or_404(folder_id)

        if item_type == 'study_plan':
            item = StudyPlan.query.get_or_404(item_id)
            if item not in folder.study_plans:
                folder.study_plans.append(item)
        elif item_type == 'document':
            item = Document.query.get_or_404(item_id)
            if item not in folder.documents:
                folder.documents.append(item)
        else:
            return jsonify({'error': 'Invalid item type'}), 400

        db.session.commit()
        return jsonify({'success': True})

    except Exception as e:
        logging.error(f"Error updating folder items: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/folders/<int:folder_id>', methods=['GET'])
def view_folder(folder_id):
    from models import Folder
    folder = Folder.query.get_or_404(folder_id)
    return render_template('folder_view.html', folder=folder)

@app.route('/interview-practice', methods=['GET'])
def interview_practice():
    """Show interview practice dashboard"""
    from models import InterviewQuestion
    # Clear existing questions if requested
    if request.args.get('clear'):
        InterviewQuestion.query.filter_by(user_id=1).delete()
        db.session.commit()
    questions = InterviewQuestion.query.filter_by(user_id=1).order_by(InterviewQuestion.created_at.desc()).all()
    return render_template('interview_practice.html', questions=questions)

@app.route('/interview-practice/generate', methods=['POST'])
def generate_interview_questions():
    try:
        from models import InterviewQuestion, InterviewPractice
        logging.info("Starting question generation process")

        data = request.get_json()
        job_description = data.get('job_description', '')
        resume = data.get('resume', '')

        logging.info(f"Received request with job description length: {len(job_description)}")

        if not job_description:
            return jsonify({'error': 'Job description is required'}), 400

        try:
            client = OpenAI()
            if not os.environ.get("OPENAI_API_KEY"):
                logging.error("OpenAI API key is not set")
                return jsonify({'error': 'OpenAI API key is not configured'}), 500

            # Clear existing questions
            InterviewQuestion.query.filter_by(user_id=1).delete()
            db.session.commit()

            # Simple, focused prompt
            prompt = """Based on the provided job description, generate 5 interview questions that assess both technical skills and behavioral competencies. Each question should have:

1. A clear, specific question
2. A sample answer that demonstrates what a strong response would look like
3. A category (Technical or Behavioral)
4. A difficulty level (Easy, Medium, or Hard)

Provide your response in this JSON format:
{
    "questions": [
        {
            "question": "The interview question text",
            "sample_answer": "A detailed example of what makes a good answer",
            "category": "Technical or Behavioral",
            "difficulty": "Easy, Medium, or Hard"
        }
    ]
}

Job Description:
"""

            logging.info("Sending request to OpenAI")
            response = client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[{
                    "role": "user",
                    "content": prompt + job_description
                }],
                temperature=0.7
            )

            content = response.choices[0].message.content.strip()
            logging.info("Received response from OpenAI")
            logging.debug(f"Full response content: {content}")

            try:
                data = json.loads(content)
                questions = data.get('questions', [])

                if not questions:
                    logging.error("No questions generated in the response")
                    return jsonify({'error': 'Failed to generate questions'}), 500

                logging.info(f"Successfully parsed {len(questions)} questions")

                # Save questions to database
                saved_questions = []
                for q in questions:
                    question = InterviewQuestion(
                        user_id=1,
                        question=q['question'],
                        sample_answer=q['sample_answer'],
                        category=q['category'],
                        difficulty=q['difficulty'],
                        job_description=job_description,
                        success_rate=85  # Default success rate
                    )
                    db.session.add(question)
                    saved_questions.append(question)

                db.session.commit()
                logging.info(f"Successfully saved {len(saved_questions)} questions")

                return jsonify({
                    'success': True,
                    'questions': [{
                        'id': q.id,
                        'question': q.question,
                        'category': q.category,
                        'difficulty': q.difficulty
                    } for q in saved_questions]
                })

            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse OpenAI response: {str(e)}")
                logging.error(f"Invalid JSON content: {content}")
                return jsonify({'error': 'Failed to generate valid interview questions'}), 500

            except Exception as e:
                logging.error(f"Error processing response: {str(e)}", exc_info=True)
                return jsonify({'error': 'Error processing the generated questions'}), 500

        except Exception as e:
            logging.error(f"OpenAI API error: {str(e)}", exc_info=True)
            return jsonify({'error': 'Failed to connect to OpenAI service'}), 500

    except Exception as e:
        logging.error(f"Error in question generation: {str(e)}", exc_info=True)
        return jsonify({'error': 'An unexpected error occurred'}), 500

@app.route('/interview-practice/<int:question_id>/answer', methods=['POST'])
def submit_practice_answer(question_id):
    """Submit and get feedback on practice answer"""
    try:
        from models import InterviewQuestion, InterviewPractice
        question = InterviewQuestion.query.get_or_404(question_id)

        logging.info(f"Processing answer submission for question {question_id}")
        logging.info(f"Form data: {request.form}")
        logging.info(f"Files: {request.files}")

        # Get answer type and content
        answer_type = request.form.get('answer_type', 'text')
        answer_content = request.form.get('answer')

        # Handle file upload for audio/video
        media_file = request.files.get('media_file')
        media_url = None

        # Validate input
        if answer_type == 'text':
            if not answer_content:
                return jsonify({'error': 'Answer text is required'}), 400
        elif answer_type in ['audio', 'video']:
            if not media_file:
                return jsonify({'error': 'Media file is required'}), 400

            # Process media file
            filename = secure_filename(f"{answer_type}_{datetime.utcnow().timestamp()}.webm")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            media_file.save(filepath)
            media_url = filename
            answer_content = f"[{answer_type.upper()} Response]"

        # Generate AI feedback
        try:
            client = OpenAI()
            prompt = f"""Evaluate this interview answer and provide constructive feedback.

Question: {question.question}
Sample Answer: {question.sample_answer}
User's Answer: {answer_content}
Answer Type: {answer_type}

Provide feedback in this format:
- What was good about the answer
- What could be improved
- Overall score (0-100)
"""

            feedback_response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an expert interviewer providing constructive feedback."},
                    {"role": "user", "content": prompt}
                ]
            )

            feedback = feedback_response.choices[0].message.content

        except Exception as e:
            logging.error(f"Error generating feedback: {str(e)}")
            return jsonify({'error': 'Failed to generate feedback'}), 500

        # Generate confidence score for audio/video submissions
        confidence_score = random.randint(60, 95) if answer_type in ['audio', 'video'] else None

        # Save practice attempt
        try:
            practice = InterviewPractice(
                user_id=1,  # Default user
                question_id=question_id,
                user_answer=answer_content,
                answer_type=answer_type,
                media_url=media_url,
                ai_feedback=feedback,
                score=75,  # Default score
                confidence_score=confidence_score
            )
            db.session.add(practice)
            db.session.commit()

        except Exception as e:
            logging.error(f"Error saving practice: {str(e)}")
            return jsonify({'error': 'Failed to save practice attempt'}), 500

        # Prepare response
        feedback_data = {
            'feedback': feedback,
            'score': practice.score
        }

        if answer_type in ['audio', 'video']:
            feedback_data['confidence_score'] = confidence_score

        return jsonify({
            'success': True,
            'feedback': feedback_data
        })

    except Exception as e:
        logging.error(f"Error processing practice answer: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/interview-practice/export', methods=['POST'])
def export_interview_data():
    """Export interview practice data"""
    try:
        from models import InterviewQuestion, InterviewPractice
        user_id = 1  # Default user

        # Get all practice sessions for the user
        questions = InterviewQuestion.query.filter_by(user_id=user_id).all()
        practices = InterviewPractice.query.join(InterviewQuestion).filter(InterviewQuestion.user_id == user_id).all()

        export_data = {
            'questions': [{
                'id': q.id,
                'question': q.question,
                'category': q.category,
                'difficulty': q.difficulty,
                'job_description': q.job_description,
                'resume_content': q.resume_content,
                'success_rate': q.success_rate,
                'created_at': q.created_at.isoformat()
            } for q in questions],
            'practices': [{
                'id': p.id,
                'question_id': p.question_id,
                'answer_type': p.answer_type,
                'user_answer': p.user_answer,
                'ai_feedback': p.ai_feedback,
                'score': p.score,
                'confidence_score': p.confidence_score,
                'created_at': p.created_at.isoformat()
            } for p in practices]
        }

        return jsonify({
            'success': True,
            'data': export_data
        })

    except Exception as e:
        logging.error(f"Error exporting interview data: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/interview-practice/clear', methods=['POST'])
def clear_interview_data():
    """Clear all interview practice data"""
    try:
        from models import InterviewQuestion, InterviewPractice
        user_id = 1  # Default user

        # Delete all practice attempts and questions for the current user
        InterviewPractice.query.join(InterviewQuestion).filter(InterviewQuestion.user_id == user_id).delete()
        InterviewQuestion.query.filter_by(user_id=user_id).delete()
        db.session.commit()

        return jsonify({'success': True, 'message': 'All interview practice datahas been cleared'})

    except Exception as e:
        logging.error(f"Error clearing interview data: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Add this route after the existing routes
@app.route('/test-openai')
def test_openai():
    """Test OpenAI API connection"""
    try:
        logging.info("Testing OpenAI API connection")
        client = OpenAI()
        logging.debug(f"OpenAI API Key present: {bool(os.environ.get('OPENAI_API_KEY'))}")

        try:
            # Try a simple completion
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "user", "content": "Say 'OpenAI connection working!'"}
                ]
            )

            if response and response.choices and response.choices[0].message:
                logging.info("OpenAI API test successful")
                return jsonify({
                    'success': True,
                    'message': response.choices[0].message.content,
                    'api_status': 'working'
                })
            else:
                error_msg = "OpenAI API response was empty or invalid"
                logging.error(error_msg)
                return jsonify({
                    'success': False,
                    'error': error_msg,
                    'api_status': 'invalid_response'
                }), 500

        except Exception as api_error:
            errormsg = f"OpenAI API call failed: {str(api_error)}"
            logging.error(error_msg)
            return jsonify({
                'success': False,
                'error': error_msg,
                'api_status': 'api_error'
            }), 500

    except Exception as e:
        error_msg = f"General error in test_openai route: {str(e)}"
        logging.error(error_msg)
        return jsonify({
            'success': False,
            'error': error_msg,
            'api_status': 'setup_error'
        }), 500

# Fix app context usage
with app.app_context():
    # Import models here to avoid circular imports
    import models
    db.create_all()