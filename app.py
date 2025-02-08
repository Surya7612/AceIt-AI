import os
import logging
import random
import json
from datetime import datetime
from flask import request, jsonify, render_template, flash, redirect, url_for
from werkzeug.utils import secure_filename
from extensions import app, db, openai_client  # Import the shared client
from auth import auth as auth_blueprint
from flask_login import login_required, current_user
from subscription import subscription as subscription_blueprint, premium_required

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Register blueprint
app.register_blueprint(auth_blueprint)
app.register_blueprint(subscription_blueprint)

# Add the JSON filter at the application level
@app.template_filter('from_json')
def from_json_filter(value):
    try:
        return json.loads(value) if value else None
    except Exception as e:
        logging.error(f"JSON parsing error: {str(e)}")
        return None

# Update index route to include study plans
@app.route('/')
def index():
    """Render the home page"""
    try:
        from models import Document, StudyPlan
        # Get recent documents and study plans if user is logged in
        recent_docs = []
        recent_plans = []
        if current_user.is_authenticated:
            recent_docs = Document.query.filter_by(
                user_id=current_user.id
            ).order_by(Document.created_at.desc()).limit(3).all()

            recent_plans = StudyPlan.query.filter_by(
                user_id=current_user.id
            ).order_by(StudyPlan.created_at.desc()).limit(3).all()

        return render_template('index.html', recent_docs=recent_docs, recent_plans=recent_plans)
    except Exception as e:
        logging.error(f"Error loading home page: {str(e)}")
        return render_template('index.html', recent_docs=[], recent_plans=[])

@app.route('/study-plan/<int:plan_id>')
@login_required
def view_study_plan(plan_id):
    """View a specific study plan"""
    try:
        from models import StudyPlan
        study_plan = StudyPlan.query.get_or_404(plan_id)

        # Check if the plan belongs to the current user
        if study_plan.user_id != current_user.id:
            flash('You do not have permission to view this study plan.', 'error')
            return redirect(url_for('study_plan'))

        return render_template('study_plan_view.html', study_plan=study_plan)
    except Exception as e:
        logging.error(f"Error viewing study plan: {str(e)}")
        flash('Error loading study plan.', 'error')
        return redirect(url_for('study_plan'))

@app.route('/study-plan')
@login_required
def study_plan():
    """Render the study plans page"""
    try:
        from models import StudyPlan

        # Get all study plans for the user
        study_plans = StudyPlan.query.filter_by(user_id=current_user.id).order_by(StudyPlan.created_at.desc()).all()
        logging.info(f"Found {len(study_plans)} study plans for user {current_user.id}")

        return render_template('study_plan.html', plans=study_plans)

    except Exception as e:
        logging.error(f"Error loading study plans: {str(e)}")
        flash('Error loading study plans.', 'error')
        return render_template('study_plan.html', plans=[])

@app.route('/study-plan/<int:plan_id>/session/start', methods=['POST'])
@login_required
def start_study_session(plan_id):
    """Start a study session"""
    try:
        from models import StudyPlan, StudySession
        study_plan = StudyPlan.query.get_or_404(plan_id)

        if study_plan.user_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403

        session = StudySession(
            user_id=current_user.id,
            study_plan_id=plan_id,
            start_time=datetime.utcnow()
        )
        db.session.add(session)
        db.session.commit()

        return jsonify({
            'success': True,
            'session_id': session.id
        })
    except Exception as e:
        logging.error(f"Error starting study session: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/study-plan/<int:plan_id>/session/<int:session_id>/end', methods=['POST'])
@login_required
def end_study_session(plan_id, session_id):
    """End a study session"""
    try:
        from models import StudySession
        session = StudySession.query.get_or_404(session_id)

        if session.user_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403

        session.end_time = datetime.utcnow()
        db.session.commit()

        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"Error ending study session: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/study-plan/<int:plan_id>/delete', methods=['POST'])
@login_required
def delete_study_plan(plan_id):
    """Delete a study plan"""
    try:
        from models import StudyPlan
        study_plan = StudyPlan.query.get_or_404(plan_id)

        if study_plan.user_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403

        db.session.delete(study_plan)
        db.session.commit()

        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"Error deleting study plan: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/documents')
@login_required
def documents():
    """Render the documents page"""
    return render_template('documents.html')

@app.route('/folders')
@login_required
def folders():
    """Render the folders page"""
    try:
        from models import StudyPlan, Document, Folder

        # Get all folders for the user
        folders = Folder.query.filter_by(user_id=current_user.id).all()

        # Get unorganized study plans and documents
        study_plans = StudyPlan.query.filter_by(
            user_id=current_user.id
        ).filter(~StudyPlan.folders.any()).all()

        documents = Document.query.filter_by(
            user_id=current_user.id
        ).filter(~Document.folders.any()).all()

        return render_template('folders.html', 
                            folders=folders,
                            study_plans=study_plans,
                            documents=documents)
    except Exception as e:
        logging.error(f"Error loading folders: {str(e)}")
        return render_template('folders.html', 
                            folders=[],
                            study_plans=[],
                            documents=[])

@app.route('/folders', methods=['POST'])
@login_required
def create_folder():
    """Create a new folder"""
    try:
        from models import Folder
        data = request.get_json()

        if not data or 'name' not in data:
            return jsonify({'error': 'Name is required'}), 400

        folder = Folder(
            user_id=current_user.id,
            name=data['name']
        )
        db.session.add(folder)
        db.session.commit()

        return jsonify({'success': True, 'folder_id': folder.id})
    except Exception as e:
        logging.error(f"Error creating folder: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/folders/<int:folder_id>/items', methods=['POST'])
@login_required
def add_to_folder(folder_id):
    """Add an item to a folder"""
    try:
        from models import Folder, StudyPlan, Document
        folder = Folder.query.get_or_404(folder_id)

        if folder.user_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403

        data = request.get_json()
        if not data or 'type' not in data or 'id' not in data:
            return jsonify({'error': 'Invalid request data'}), 400

        item_id = int(data['id'])
        if data['type'] == 'study_plan':
            item = StudyPlan.query.get_or_404(item_id)
        elif data['type'] == 'document':
            item = Document.query.get_or_404(item_id)
        else:
            return jsonify({'error': 'Invalid item type'}), 400

        if item.user_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403

        folder.items.append(item)
        db.session.commit()

        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"Error adding item to folder: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/interview-practice')
@login_required
def interview_practice():
    """Render the interview practice page"""
    from models import InterviewQuestion
    questions = InterviewQuestion.query.filter_by(user_id=current_user.id).all()
    return render_template('interview_practice.html', questions=questions)

@app.route('/interview-practice/generate', methods=['POST'])
@login_required
def generate_interview_questions():
    """Generate interview questions based on job description"""
    try:
        from models import InterviewQuestion, InterviewPractice
        logging.info("Starting question generation process")

        data = request.get_json()
        if not data:
            logging.error("No JSON data received")
            return jsonify({'error': 'No data provided', 'success': False}), 400

        job_description = data.get('job_description', '')
        resume = data.get('resume', '')

        if not job_description:
            logging.error("No job description provided")
            return jsonify({'error': 'Job description is required', 'success': False}), 400

        # Delete practices first to avoid FK constraint violation
        try:
            logging.info("Cleaning up existing practice records")
            InterviewPractice.query.filter(
                InterviewPractice.question_id.in_(
                    db.session.query(InterviewQuestion.id).filter_by(user_id=current_user.id)
                )
            ).delete(synchronize_session=False)
            db.session.commit()

            logging.info("Cleaning up existing questions")
            InterviewQuestion.query.filter_by(user_id=current_user.id).delete()
            db.session.commit()
        except Exception as db_error:
            logging.error(f"Database cleanup error: {str(db_error)}")
            db.session.rollback()
            return jsonify({'error': 'Database error during cleanup', 'success': False}), 500

        # Generate compatibility analysis if resume is provided
        compatibility = None
        if resume:
            try:
                compatibility_prompt = f"""As an ATS (Applicant Tracking System) expert, analyze the compatibility between this resume and job description:

Resume:
{resume[:1000]}

Job Description:
{job_description[:500]}

Provide a detailed ATS analysis in this exact JSON format:
{{
    "compatibility_score": (overall match percentage between 0-100),
    "ats_score": (ATS readability score between 0-100),
    "keyword_match_rate": (percentage of key terms matched between 0-100),
    "strengths": [list of 3-5 key matching strengths with specific examples],
    "gaps": [list of 2-3 missing skills or experiences],
    "key_matches": [list of 4-5 important keywords found in both],
    "missing_keywords": [list of 3-4 important keywords from job description not found in resume],
    "format_suggestions": [list of 2-3 ATS-friendly formatting suggestions if any]
}}"""

                compatibility_response = openai_client.chat.completions.create(
                    model="gpt-4", # Changed to gpt-4
                    messages=[
                        {"role": "system", "content": "You are an expert ATS analyst specializing in technical roles."},
                        {"role": "user", "content": compatibility_prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7
                )

                compatibility = json.loads(compatibility_response.choices[0].message.content)
                logging.info("Generated ATS compatibility analysis")

            except Exception as analysis_error:
                logging.error(f"Error generating compatibility analysis: {str(analysis_error)}")
                # Continue without compatibility analysis if it fails

        # Generate interview questions
        questions_prompt = f"""Generate 5 interview questions based on this job description:

{job_description[:500]}

For each question, use this EXACT format with no variations:

Question: [The interview question]
Category: [Technical/Behavioral]
Difficulty: [Easy/Medium/Hard]

Generate exactly 5 questions."""

        logging.info("Sending request to OpenAI")
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4", # Changed to gpt-4
                messages=[
                    {"role": "system", "content": "You are an expert interviewer generating questions."},
                    {"role": "user", "content": questions_prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )

            content = response.choices[0].message.content
            logging.info(f"Received response from OpenAI: {content}")

        except Exception as openai_error:
            logging.error(f"OpenAI API error: {str(openai_error)}")
            return jsonify({'error': f'Failed to generate questions: {str(openai_error)}', 'success': False}), 500

        # Parse questions
        questions = []
        current_question = {}

        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue

            if line.startswith('Question:'):
                if current_question:
                    questions.append(current_question)
                current_question = {'question': line[9:].strip()}
            elif line.startswith('Category:'):
                current_question['category'] = line[9:].strip()
            elif line.startswith('Difficulty:'):
                current_question['difficulty'] = line[11:].strip()
                questions.append(current_question)
                current_question = {}

        if not questions:
            logging.error(f"Failed to parse questions from response: {content}")
            return jsonify({'error': 'Failed to generate valid questions', 'success': False}), 500

        logging.info(f"Successfully parsed {len(questions)} questions")

        # Save questions to database
        saved_questions = []
        try:
            for q in questions:
                if all(k in q for k in ['question', 'category', 'difficulty']):
                    question = InterviewQuestion(
                        user_id=current_user.id,
                        question=q['question'],
                        category=q['category'],
                        difficulty=q['difficulty'],
                        job_description=job_description[:500],
                        success_rate=random.randint(75, 95)
                    )
                    db.session.add(question)
                    saved_questions.append(question)

            db.session.commit()
            logging.info(f"Successfully saved {len(saved_questions)} questions")

            response_data = {
                'success': True,
                'questions': [{
                    'id': q.id,
                    'question': q.question,
                    'category': q.category,
                    'difficulty': q.difficulty,
                    'success_rate': q.success_rate
                } for q in saved_questions]
            }

            if compatibility:
                response_data['compatibility'] = compatibility

            return jsonify(response_data)

        except Exception as db_error:
            logging.error(f"Database error while saving questions: {str(db_error)}")
            db.session.rollback()
            return jsonify({'error': 'Failed to save questions to database', 'success': False}), 500

    except Exception as e:
        logging.error(f"General error in question generation: {str(e)}")
        return jsonify({'error': str(e), 'success': False}), 500

@app.route('/test-openai')
def test_openai():
    """Test OpenAI API connection"""
    try:
        logging.info("Testing OpenAI API connection")
        logging.debug(f"OpenAI API Key present: {bool(os.environ.get('OPENAI_API_KEY'))}")

        response = openai_client.chat.completions.create(
            model="gpt-4",  # Using standard gpt-4 model
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
            logging.error("Invalid response format from OpenAI")
            return jsonify({
                'success': False,
                'error': 'Invalid response format',
                'api_status': 'error'
            }), 500

    except Exception as e:
        logging.error(f"Error testing OpenAI connection: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'api_status': 'error'
        }), 500


@app.route('/interview-practice/<int:question_id>/answer', methods=['POST'])
@login_required
def submit_answer(question_id):
    """Submit an answer for an interview question"""
    try:
        from models import InterviewPractice, InterviewQuestion
        logging.info("Starting answer submission process")

        # Get the question
        question = InterviewQuestion.query.get_or_404(question_id)

        answer_type = request.form.get('answer_type')
        if not answer_type:
            return jsonify({'error': 'Answer type is required'}), 400

        # Restrict audio/video responses to premium users
        if answer_type in ['audio', 'video'] and not current_user.is_premium:
            return jsonify({
                'error': 'Audio and video responses are premium features. Please upgrade your subscription.',
                'premium_required': True
            }), 403

        # Get next attempt number
        attempt_number = InterviewPractice.get_next_attempt_number(current_user.id, question_id)

        # Create practice record
        practice = InterviewPractice(
            user_id=current_user.id,
            question_id=question_id,
            answer_type=answer_type,
            attempt_number=attempt_number
        )

        if answer_type == 'text':
            answer = request.form.get('answer')
            if not answer:
                return jsonify({'error': 'Answer is required'}), 400
            practice.user_answer = answer

        else:  # audio or video
            if 'media_file' not in request.files:
                return jsonify({'error': 'Media file is required'}), 400

            file = request.files['media_file']
            if file.filename == '':
                return jsonify({'error': 'No selected file'}), 400

            # Save with attempt number in filename
            filename = secure_filename(f"{question_id}_attempt_{attempt_number}_{datetime.utcnow().timestamp()}.webm")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            practice.media_url = filename

            # Transcribe audio from media file
            try:
                with open(filepath, "rb") as audio_file:
                    transcript = openai_client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file
                    )
                practice.user_answer = transcript.text
                logging.info(f"Transcribed answer: {practice.user_answer}")
            except Exception as e:
                logging.error(f"Error transcribing audio: {str(e)}")
                practice.user_answer = f"[{answer_type.upper()} Response - Transcription Failed]"

        # Generate AI feedback for answer
        feedback_prompt = f"""As an expert interview assessor, analyze this interview answer:

Question: {question.question}
Expected Answer: {question.sample_answer}
User's Answer: {practice.user_answer}
Category: {question.category}
Attempt Number: {attempt_number}

You MUST format your response as a valid JSON object with exactly these fields:
{{
    "score": (a number between 0 and 100),
    "feedback": "detailed analysis of the answer",
    "confidence_score": (a number between 0 and 100, required for audio/video responses)
}}

Respond ONLY with the JSON object, no additional text."""

        try:
            logging.info("Sending feedback request to OpenAI")
            response = openai_client.chat.completions.create(
                model="gpt-4", # Changed to gpt-4
                messages=[
                    {"role": "system", "content": "You are an expert interview assessor. You must return only valid JSON."},
                    {"role": "user", "content": feedback_prompt}
                ],
                temperature=0.3  # Lower temperature for more consistent formatting
            )

            # Log the raw response
            feedback_data = response.choices[0].message.content
            logging.debug(f"Raw feedback response: {feedback_data}")

            try:
                feedback_dict = json.loads(feedback_data.strip())

                # Validate response format
                required_fields = ['score', 'feedback']
                if answer_type in ['audio', 'video']:
                    required_fields.append('confidence_score')

                if not all(k in feedback_dict for k in required_fields):
                    raise ValueError(f"Missing required fields. Got: {list(feedback_dict.keys())}")

                # Validate and normalize scores
                feedback_dict['score'] = max(0, min(100, float(feedback_dict['score'])))
                if 'confidence_score' in feedback_dict:
                    feedback_dict['confidence_score'] = max(0, min(100, float(feedback_dict['confidence_score'])))

            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse OpenAI response as JSON: {str(e)}")
                return jsonify({'error': 'Invalid feedback format from AI'}), 500
            except ValueError as e:
                logging.error(f"Invalid feedback format: {str(e)}")
                return jsonify({'error': str(e)}), 500

            practice.score = feedback_dict['score']
            practice.ai_feedback = feedback_dict['feedback']
            if answer_type in ['audio', 'video']:
                practice.confidence_score = feedback_dict.get('confidence_score', 0)

            db.session.add(practice)
            db.session.commit()

            return jsonify({
                'success': True,
                'feedback': {
                    'score': practice.score,
                    'feedback': practice.ai_feedback,
                    'confidence_score': practice.confidence_score if answer_type in ['audio', 'video'] else None,
                    'attempt_number': practice.attempt_number
                }
            })

        except Exception as e:
            logging.error(f"Error generating AI feedback: {str(e)}")
            db.session.rollback()
            return jsonify({'error': f'Failed to generate AI feedback: {str(e)}'}), 500

    except Exception as e:
        logging.error(f"Error submitting answer: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/interview-practice/export', methods=['POST'])
@login_required
def export_interview_data():
    """Export interview practice data"""
    try:
        from models import InterviewQuestion, InterviewPractice
        logging.info("Starting data export process")

        # Get all questions and their practices for the current user
        questions = InterviewQuestion.query.filter_by(user_id=current_user.id).all()

        export_data = []
        for question in questions:
            practices = InterviewPractice.query.filter_by(
                user_id=current_user.id,
                question_id=question.id
            ).order_by(InterviewPractice.attempt_number).all()

            question_data = {
                'question': question.question,
                'category': question.category,
                'difficulty': question.difficulty,
                'sample_answer': question.sample_answer,
                'practices': [{
                    'attempt_number': p.attempt_number,
                    'answer_type': p.answer_type,
                    'user_answer': p.user_answer,
                    'score': p.score,
                    'ai_feedback': p.ai_feedback,
                    'confidence_score': p.confidence_score if p.answer_type in ['audio', 'video'] else None,
                    'created_at': p.created_at.isoformat()
                } for p in practices]
            }
            export_data.append(question_data)

        return jsonify({
            'success': True,
            'data': export_data
        })

    except Exception as e:
        logging.error(f"Error exporting data: {str(e)}")
        return jsonify({'error': str(e), 'success': False}), 500

@app.route('/interview-practice/clear', methods=['POST'])
@login_required
def clear_interview_data():
    """Clear all interview practice data"""
    try:
        from models import InterviewQuestion, InterviewPractice
        logging.info("Starting data clear process")

        # First delete practices to avoid FK constraint violations
        InterviewPractice.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()

        # Then delete questions
        InterviewQuestion.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()

        return jsonify({'success': True})

    except Exception as e:
        logging.error(f"Error clearing data: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e), 'success': False}), 500

@app.route('/study-plan', methods=['POST'])
@login_required
def create_study_plan():
    """Create a new study plan"""
    try:
        from models import StudyPlan, Document
        from ai_helper import generate_study_schedule
        logging.info("Starting study plan creation process")

        # Get form data
        data = request.form.to_dict()
        logging.debug(f"Received form data: {data}")

        # Basic validation
        required_fields = ['topic', 'priority', 'daily_time', 'completion_date', 'difficulty', 'goals']
        for field in required_fields:
            if field not in data:
                logging.error(f"Missing required field: {field}")
                return jsonify({'error': f'Missing required field: {field}', 'success': False}), 400

        # Process uploaded files if any
        uploaded_documents = []
        if 'files' in request.files:
            files = request.files.getlist('files')
            for file in files:
                if file and file.filename:
                    try:
                        filename = secure_filename(file.filename)
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(filepath)

                        # Create document record
                        document = Document(
                            user_id=current_user.id,
                            original_filename=filename,
                            file_path=filepath,
                            processed=False
                        )
                        db.session.add(document)
                        db.session.commit()
                        uploaded_documents.append(document)
                    except Exception as e:
                        logging.error(f"Error processing uploaded file: {e}")
                        continue

        try:
            # Generate AI study schedule with documents if available
            schedule = generate_study_schedule(
                topic=data['topic'],
                priority=int(data['priority']),
                daily_time=int(data['daily_time']),
                completion_date=data['completion_date'],
                difficulty=data['difficulty'],
                goals=data['goals'],
                documents=uploaded_documents,
                link=data.get('link')
            )

            # Create study plan with generated schedule
            study_plan = StudyPlan(
                user_id=current_user.id,
                title=data['topic'],
                category=schedule.get('category', 'General'),
                content=json.dumps(schedule),
                priority=int(data['priority']),
                daily_study_time=int(data['daily_time']),
                completion_target=datetime.strptime(data['completion_date'], '%Y-%m-%d'),
                difficulty_level=data['difficulty']
            )

            db.session.add(study_plan)
            db.session.commit()
            logging.info(f"Successfully created study plan with ID: {study_plan.id}")

            return jsonify({
                'success': True,
                'plan_id': study_plan.id
            })

        except Exception as db_error:
            logging.error(f"Database error while creating study plan: {str(db_error)}")
            db.session.rollback()
            return jsonify({'error': 'Failed to save study plan to database', 'success': False}), 500

    except Exception as e:
        logging.error(f"Error creating study plan: {str(e)}")
        return jsonify({'error': str(e), 'success': False}), 500

@app.route('/chat', methods=['POST'])
@login_required
def chat():
    """Handle chat messages and return AI responses"""
    try:
        from models import ChatHistory
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'No message provided'}), 400

        message = data['message']
        tutor_mode = data.get('tutor_mode', False)
        logging.info(f"Processing chat message, tutor mode: {tutor_mode}")

        # Get relevant context if tutor mode is enabled
        context = None
        if tutor_mode:
            from ai_helper import get_relevant_context
            context = get_relevant_context(message, current_user.id)
            if context:
                context = "Here's some relevant information from the user's materials:\n" + \
                         "\n".join([f"From {item['title']}:\n{item['content']}" for item in context])

        # Generate response using AI helper
        from ai_helper import chat_response
        try:
            response = chat_response(message, context, tutor_mode, current_user.id)

            # Save chat history
            chat_record = ChatHistory(
                user_id=current_user.id,
                question=message,
                answer=response
            )
            db.session.add(chat_record)
            db.session.commit()

            return jsonify({
                'response': response,
                'success': True
            })

        except Exception as e:
            logging.error(f"Error generating chat response: {str(e)}")
            return jsonify({
                'error': 'Failed to generate response',
                'details': str(e)
            }), 500

    except Exception as e:
        logging.error(f"Error in chat endpoint: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Initialize database
with app.app_context():
    import models
    db.create_all()