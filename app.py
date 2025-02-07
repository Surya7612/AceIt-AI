import os
import logging
import random
import json
from datetime import datetime
from flask import request, jsonify, render_template
from werkzeug.utils import secure_filename
from openai import OpenAI
from extensions import app, db

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    """Render the home page"""
    return render_template('index.html')

@app.route('/study-plan')
def study_plan():
    """Render the study plans page"""
    return render_template('study_plan.html')

@app.route('/documents')
def documents():
    """Render the documents page"""
    return render_template('documents.html')

@app.route('/folders')
def folders():
    """Render the folders page"""
    return render_template('folders.html')

@app.route('/interview-practice')
def interview_practice():
    """Render the interview practice page"""
    from models import InterviewQuestion
    questions = InterviewQuestion.query.filter_by(user_id=1).all()
    return render_template('interview_practice.html', questions=questions)

@app.route('/interview-practice/generate', methods=['POST'])
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

        try:
            if not os.environ.get("OPENAI_API_KEY"):
                logging.error("OpenAI API key is not set")
                return jsonify({'error': 'OpenAI API key is not configured'}), 500

            client = OpenAI()
            logging.debug(f"OpenAI API Key present: {bool(os.environ.get('OPENAI_API_KEY'))}")

            # First get existing practices to avoid FK constraint violation
            existing_practices = InterviewPractice.query.join(InterviewQuestion).filter(
                InterviewQuestion.user_id == 1
            ).all()

            # Delete practices first
            for practice in existing_practices:
                db.session.delete(practice)
            db.session.commit()

            # Now safe to delete questions
            InterviewQuestion.query.filter_by(user_id=1).delete()
            db.session.commit()

            # Generate compatibility analysis
            analysis_prompt = f"""Analyze the compatibility between this job description and resume:

Job Description:
{job_description}

Resume:
{resume}

Provide a JSON response with:
1. score (0-100): Overall compatibility score
2. strengths: Array of key matching strengths
3. gaps: Array of areas for improvement"""

            try:
                analysis_response = client.chat.completions.create(
                    model="gpt-4",  # Using correct model name
                    messages=[
                        {"role": "system", "content": "You are an expert job matcher."},
                        {"role": "user", "content": analysis_prompt}
                    ],
                    response_format={"type": "json_object"}
                )
                compatibility_data = json.loads(analysis_response.choices[0].message.content)
            except Exception as e:
                logging.error(f"Error generating compatibility analysis: {str(e)}")
                compatibility_data = {"score": 0, "strengths": [], "gaps": []}

            # Generate interview questions
            questions_prompt = f"""Generate 5 interview questions based on this job description:

{job_description}

For each question, provide:
1. Question text
2. Sample answer
3. Category (Technical/Behavioral)
4. Difficulty (Easy/Medium/Hard)

Format each question like this:
1. Question: [question text]
Sample Answer: [answer text]
Category: [Technical/Behavioral]
Difficulty: [Easy/Medium/Hard]
"""

            response = client.chat.completions.create(
                model="gpt-4",  # Using correct model name
                messages=[
                    {"role": "system", "content": "You are an expert interviewer. Format your response exactly as shown in the prompt."},
                    {"role": "user", "content": questions_prompt}
                ]
            )

            content = response.choices[0].message.content
            logging.info(f"Received response from OpenAI: {content[:200]}...")

            questions = []
            current_question = {}

            # Parse the response
            question_blocks = content.split('\n\n')
            for block in question_blocks:
                if not block.strip():
                    continue

                if block.strip().startswith(('1.', '2.', '3.', '4.', '5.')):
                    if current_question:
                        questions.append(current_question)
                        current_question = {}

                    lines = block.strip().split('\n')
                    question_line = lines[0]
                    if ': ' in question_line:
                        current_question['question'] = question_line.split(': ', 1)[1].strip()
                    elif '. ' in question_line:
                        current_question['question'] = question_line.split('. ', 1)[1].strip()

                    for line in lines[1:]:
                        line = line.strip()
                        if 'Sample Answer:' in line:
                            current_question['sample_answer'] = line.split(':', 1)[1].strip()
                        elif 'Category:' in line:
                            current_question['category'] = line.split(':', 1)[1].strip()
                        elif 'Difficulty:' in line:
                            current_question['difficulty'] = line.split(':', 1)[1].strip()

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
                        user_id=1,
                        question=q['question'],
                        sample_answer=q.get('sample_answer', 'Not provided'),
                        category=q.get('category', 'General'),
                        difficulty=q.get('difficulty', 'Medium'),
                        job_description=job_description,
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
                } for q in saved_questions],
                'compatibility_ranking': compatibility_data
            })

        except Exception as api_error:
            logging.error(f"OpenAI API error: {str(api_error)}")
            return jsonify({'error': 'Failed to generate questions with OpenAI'}), 500

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

        # Get next attempt number
        attempt_number = InterviewPractice.get_next_attempt_number(1, question_id)  # User ID hardcoded for now

        # Create practice record
        practice = InterviewPractice(
            user_id=1,  # Hardcoded for now
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
            practice.user_answer = f"[{answer_type.upper()} Response]"

        # Generate AI feedback
        try:
            client = OpenAI()
            logging.debug(f"OpenAI API Key present: {bool(os.environ.get('OPENAI_API_KEY'))}")
            # Prepare prompt based on question type
            context = f"""Question: {question.question}
Expected Answer: {question.sample_answer}
User's Answer: {practice.user_answer}
Category: {question.category}
Attempt Number: {attempt_number}"""

            prompt = f"""Analyze this interview answer and provide feedback:
{context}
Provide feedback in JSON format with these fields:
1. score (0-100)
2. feedback (detailed analysis)
3. confidence_score (0-100, only for audio/video)"""

            logging.info("Sending feedback request to OpenAI")
            response = client.chat.completions.create(
                model="gpt-4",  # Updated to latest model
                messages=[
                    {"role": "system", "content": "You are an expert interview assessor."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )

            feedback_data = response.choices[0].message.content
            logging.info(f"Received feedback from OpenAI: {feedback_data}")

            try:
                feedback_dict = json.loads(feedback_data)
            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse OpenAI response as JSON: {str(e)}")
                return jsonify({'error': 'Invalid feedback format from AI'}), 500

            practice.score = feedback_dict.get('score', 0)
            practice.ai_feedback = feedback_dict.get('feedback', '')
            if answer_type in ['audio', 'video']:
                practice.confidence_score = feedback_dict.get('confidence_score', 0)

            db.session.add(practice)
            db.session.commit()

            return jsonify({
                'success': True,
                'feedback': {
                    'score': practice.score,
                    'feedback': practice.ai_feedback,
                    'confidence_score': practice.confidence_score if hasattr(practice, 'confidence_score') else None,
                    'attempt_number': practice.attempt_number
                }
            })

        except Exception as e:
            logging.error(f"Error generating AI feedback: {str(e)}")
            db.session.rollback()
            return jsonify({'error': 'Failed to generate AI feedback'}), 500

    except Exception as e:
        logging.error(f"Error submitting answer: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Initialize database
with app.app_context():
    import models
    db.create_all()