import os
import logging
import random
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
        from models import InterviewQuestion
        logging.info("Starting question generation process")

        data = request.get_json()
        job_description = data.get('job_description', '')

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

            # Simple, clear prompt
            prompt = f"""Generate 5 interview questions based on this job description:

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

            logging.info("Sending request to OpenAI")
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an expert interviewer. Format your response exactly as shown in the prompt."},
                    {"role": "user", "content": prompt}
                ]
            )

            content = response.choices[0].message.content
            logging.info(f"Received response from OpenAI: {content[:200]}...")

            questions = []
            current_question = {}

            try:
                # Split into question blocks
                question_blocks = content.split('\n\n')

                for block in question_blocks:
                    if not block.strip():
                        continue

                    # Start new question if we see a number
                    if block.strip().startswith(('1.', '2.', '3.', '4.', '5.')):
                        if current_question:
                            questions.append(current_question)
                            current_question = {}

                        lines = block.strip().split('\n')

                        # Extract question text
                        question_line = lines[0]
                        if ': ' in question_line:
                            current_question['question'] = question_line.split(': ', 1)[1].strip()
                        elif '. ' in question_line:
                            current_question['question'] = question_line.split('. ', 1)[1].strip()

                        # Process remaining lines
                        for line in lines[1:]:
                            line = line.strip()
                            if 'Sample Answer:' in line:
                                current_question['sample_answer'] = line.split(':', 1)[1].strip()
                            elif 'Category:' in line:
                                current_question['category'] = line.split(':', 1)[1].strip()
                            elif 'Difficulty:' in line:
                                current_question['difficulty'] = line.split(':', 1)[1].strip()

                # Add last question
                if current_question:
                    questions.append(current_question)

                if not questions:
                    logging.error("No questions were parsed from the response")
                    return jsonify({'error': 'Failed to generate questions'}), 500

                # Save questions to database
                saved_questions = []
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
                        success_rate=85
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
                        'difficulty': q.difficulty,
                        'success_rate': q.success_rate
                    } for q in saved_questions]
                })

            except Exception as parse_error:
                logging.error(f"Error parsing questions: {str(parse_error)}")
                logging.error(f"Content being parsed: {content}")
                return jsonify({'error': 'Failed to parse generated questions'}), 500

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

# Initialize database
with app.app_context():
    import models
    db.create_all()