import os
import logging
import random
import json
from datetime import datetime
from flask import request, jsonify, render_template
from werkzeug.utils import secure_filename
from openai import OpenAI
from extensions import app, db
from auth import auth as auth_blueprint
from flask_login import login_required, current_user
from subscription import subscription as subscription_blueprint, premium_required # Added import and premium_required

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Register blueprint
app.register_blueprint(auth_blueprint)
app.register_blueprint(subscription_blueprint) # Added blueprint registration

@app.route('/')
def index():
    """Render the home page"""
    return render_template('index.html')

@app.route('/study-plan')
@login_required
def study_plan():
    """Render the study plans page"""
    return render_template('study_plan.html')

@app.route('/documents')
@login_required
def documents():
    """Render the documents page"""
    return render_template('documents.html')

@app.route('/folders')
@login_required
def folders():
    """Render the folders page"""
    return render_template('folders.html')

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
        job_description = data.get('job_description', '')
        resume = data.get('resume', '')

        if not job_description:
            return jsonify({'error': 'Job description is required'}), 400

        # Check existing questions count for free users
        if not current_user.is_premium:
            existing_questions_count = InterviewQuestion.query.filter_by(user_id=current_user.id).count()
            if existing_questions_count >= 5:  # Limit for free users
                return jsonify({
                    'error': 'Free users are limited to 5 questions. Upgrade to premium for unlimited questions.',
                    'premium_required': True
                }), 403

        # First get existing practices to avoid FK constraint violation
        existing_practices = InterviewPractice.query.join(InterviewQuestion).filter(
            InterviewQuestion.user_id == current_user.id
        ).all()

        # Delete practices first
        for practice in existing_practices:
            db.session.delete(practice)
        db.session.commit()

        # Now safe to delete questions
        InterviewQuestion.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()

        if not os.environ.get("OPENAI_API_KEY"):
            logging.error("OpenAI API key is not set")
            return jsonify({'error': 'OpenAI API key is not configured'}), 500

        client = OpenAI()
        logging.debug(f"OpenAI API Key present: {bool(os.environ.get('OPENAI_API_KEY'))}")

        # Generate interview questions with optimized prompt
        num_questions = 3 if not current_user.is_premium else 5
        questions_prompt = f"""Generate exactly {num_questions} focused interview questions for this job. Format as:

1. Question: [brief question]
Sample Answer: [concise answer]
Category: [Technical/Behavioral]
Difficulty: [Easy/Medium/Hard]

Job Description: {job_description[:500]}"""  # Limit job description length

        start_time = datetime.utcnow()
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a concise interviewer. Format exactly as shown."},
                {"role": "user", "content": questions_prompt}
            ],
            temperature=0.5,  # Reduced for faster responses
            max_tokens=1000   # Limited tokens for faster response
        )
        end_time = datetime.utcnow()

        logging.info(f"OpenAI API response time: {(end_time - start_time).total_seconds()} seconds")

        content = response.choices[0].message.content
        logging.debug(f"Questions response: {content[:200]}...")

        questions = []
        current_question = {}

        # Parse the response
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue

            if line.startswith(('1.', '2.', '3.', '4.', '5.')):
                if current_question:
                    questions.append(current_question)
                    current_question = {}
                continue

            for field in ['Question:', 'Sample Answer:', 'Category:', 'Difficulty:']:
                if line.startswith(field):
                    key = field.lower().replace(':', '').strip()
                    value = line[len(field):].strip()
                    current_question[key] = value
                    break

        if current_question:
            questions.append(current_question)

        if not questions:
            logging.error("No questions were parsed from the response")
            return jsonify({'error': 'Failed to generate questions'}), 500

        # Save questions to database
        saved_questions = []
        try:
            for q in questions:
                if 'question' not in q:
                    continue

                question = InterviewQuestion(
                    user_id=current_user.id,
                    question=q.get('question', ''),
                    sample_answer=q.get('sample answer', 'Not provided'),
                    category=q.get('category', 'General'),
                    difficulty=q.get('difficulty', 'Medium'),
                    job_description=job_description[:500],  # Limit stored job description
                    success_rate=random.randint(75, 95)  # Sample success rate
                )
                db.session.add(question)
                saved_questions.append(question)

            db.session.commit()
            logging.info(f"Successfully saved {len(saved_questions)} questions")
        except Exception as db_error:
            logging.error(f"Database error: {str(db_error)}")
            db.session.rollback()
            return jsonify({'error': 'Failed to save questions to database'}), 500

        return jsonify({
            'success': True,
            'questions': [{
                'id': q.id,
                'question': q.question,
                'category': q.category,
                'difficulty': q.difficulty,
                'success_rate': q.success_rate
            } for q in saved_questions]
        })

    except Exception as e:
        logging.error(f"General error in question generation: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/test-openai')
def test_openai():
    """Test OpenAI API connection"""
    try:
        logging.info("Testing OpenAI API connection")
        client = OpenAI()
        logging.debug(f"OpenAI API Key present: {bool(os.environ.get('OPENAI_API_KEY'))}")

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

        # Initialize OpenAI client at the start
        if not os.environ.get("OPENAI_API_KEY"):
            logging.error("OpenAI API key is not set")
            return jsonify({'error': 'OpenAI API key is not configured'}), 500

        client = OpenAI()
        logging.debug(f"OpenAI API Key present: {bool(os.environ.get('OPENAI_API_KEY'))}")

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
                    transcript = client.audio.transcriptions.create(
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
            response = client.chat.completions.create(
                model="gpt-4",
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

# Initialize database
with app.app_context():
    import models
    db.create_all()