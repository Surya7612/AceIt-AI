import os
import json
import logging
from datetime import datetime, timedelta
from extensions import openai_client
from cache_helper import cache_data, get_cached_data
from models import Document, StudyPlan

def generate_study_schedule(topic, priority, daily_time, completion_date, difficulty, goals, documents=None, link=None):
    """Generate an optimized study plan based on user preferences and optional documents"""
    try:
        # Initialize context from documents if provided
        context = ""
        has_materials = False

        if documents:
            for doc in documents:
                if doc.structured_content:
                    content = json.loads(doc.structured_content)
                    context += f"\nDocument: {doc.original_filename}\n{content.get('summary', '')}\n"
                    has_materials = True

        if link:
            context += f"\nProvided resource link: {link}\n"
            has_materials = True

        # Calculate study duration in days
        target_date = datetime.strptime(completion_date, '%Y-%m-%d')
        days_until_target = (target_date - datetime.now()).days

        # Define priority characteristics
        priority_level = {
            1: "high intensity with comprehensive coverage",
            2: "medium intensity with balanced coverage",
            3: "low intensity focusing on fundamentals"
        }.get(int(priority), "medium intensity with balanced coverage")

        messages = [
            {
                "role": "system",
                "content": f"""You are an expert study plan creator. Create a study plan for {topic} with {priority_level}.

Your output must be valid JSON with this structure:
{{
    "title": "{topic}",
    "summary": "Brief overview of the study approach",
    "difficulty_level": "{difficulty}",
    "estimated_total_hours": number,
    "key_concepts": [
        {{
            "name": "string",
            "description": "string",
            "priority": "high/medium/low",
            "estimated_time": number
        }}
    ],
    "learning_path": [
        {{
            "day": number,
            "topics": ["string"],
            "activities": [
                {{
                    "type": "study/practice/review",
                    "description": "string",
                    "duration_minutes": number
                }}
            ]
        }}
    ],
    "practice_questions": [
        {{
            "question": "string",
            "answer": "string",
            "difficulty": "easy/medium/hard"
        }}
    ]
}}"""
            },
            {
                "role": "user",
                "content": f"""Create a study plan for:
Topic: {topic}
Daily study time: {daily_time} minutes
Days until completion: {days_until_target}
Priority level: {priority}
Difficulty: {difficulty}
Goals: {goals}

Requirements:
1. Plan should fit within {daily_time} minutes daily sessions
2. Match the {difficulty} difficulty level
3. Content should focus on {topic} interview preparation
4. Include at least 3 key concepts and 5 practice questions
5. Break down activities into {daily_time}-minute sessions"""
            }
        ]

        if has_materials:
            messages[1]["content"] += f"\nUse this additional context:\n{context}"

        logging.info("Generating study plan with OpenAI")
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7,
            max_tokens=2000
        )

        logging.debug(f"OpenAI response: {response.choices[0].message.content}")

        # Parse and validate response
        try:
            content = response.choices[0].message.content
            schedule = json.loads(content)

            # Validate required fields
            required_fields = ["title", "summary", "key_concepts", "learning_path", "practice_questions"]
            if not all(field in schedule for field in required_fields):
                raise ValueError("Missing required fields in schedule")

            # Validate content requirements
            if len(schedule["key_concepts"]) < 3:
                raise ValueError("Not enough key concepts")
            if len(schedule["practice_questions"]) < 5:
                raise ValueError("Not enough practice questions")

            return schedule

        except json.JSONDecodeError as je:
            logging.error(f"JSON parsing error: {str(je)}\nContent: {content}")
            raise Exception("Failed to generate valid study schedule format")
        except Exception as e:
            logging.error(f"Validation error: {str(e)}")
            raise Exception(f"Failed to validate study schedule: {str(e)}")

    except Exception as e:
        logging.error(f"Study plan generation error: {str(e)}")
        raise

def get_relevant_context(query, user_id=1):
    """Retrieve relevant context from user's documents and study plans"""
    cache_key = f"context_{user_id}_{hash(query)}"
    cached_context = get_cached_data(cache_key)
    if cached_context:
        return cached_context

    context_data = []
    # Get relevant documents
    documents = Document.query.filter_by(user_id=user_id, processed=True).all()
    study_plans = StudyPlan.query.filter_by(user_id=user_id).all()

    # Extract content from documents
    for doc in documents:
        if doc.structured_content:
            content = json.loads(doc.structured_content)
            context_data.append({
                'type': 'document',
                'title': content.get('title', doc.original_filename),
                'content': content.get('summary', '')
            })

    # Extract content from study plans
    for plan in study_plans:
        if plan.content:
            content = json.loads(plan.content)
            context_data.append({
                'type': 'study_plan',
                'title': plan.title,
                'content': content.get('summary', '')
            })

    if context_data:
        cache_data(cache_key, context_data, 3600)  # Cache for 1 hour
    return context_data

def chat_response(message, context=None, tutor_mode=False, user_id=1):
    """Generate chat responses with optional tutor mode using document context"""
    try:
        messages = [
            {
                "role": "system",
                "content": "You are a helpful study assistant. "
                + ("As a tutor, reference relevant materials from the user's documents and provide detailed explanations. "
                   if tutor_mode else "Provide clear, concise answers to help students understand concepts better.")
            }
        ]

        # Add context if provided
        if context and (tutor_mode or "document" in message.lower() or "uploaded" in message.lower()):
            messages.append({
                "role": "system",
                "content": context
            })

        messages.append({"role": "user", "content": message})

        # Enhanced logging for debugging
        logging.debug(f"Sending chat request with tutor_mode={tutor_mode}")
        logging.debug(f"Context available: {bool(context)}")

        response = openai_client.chat.completions.create(
            model="gpt-4",  # Using standard gpt-4 model
            messages=messages
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"Failed to generate chat response: {e}")
        raise Exception(f"Failed to generate chat response: {e}")

def update_study_plan(plan_id, updates):
    """Update study plan schedule with AI optimization"""
    try:
        study_plan = StudyPlan.query.get(plan_id)
        if not study_plan:
            raise ValueError("Study plan not found")

        current_schedule = study_plan.get_schedule()
        if not current_schedule:
            return False

        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": """Update the study schedule based on the provided changes while maintaining overall learning objectives.
                    Optimize the schedule to accommodate the changes while ensuring effective learning progression."""
                },
                {
                    "role": "user",
                    "content": f"""Current schedule: {json.dumps(current_schedule)}
                    Requested updates: {json.dumps(updates)}
                    Daily study time: {study_plan.daily_study_time} minutes
                    Priority level: {study_plan.priority}
                    Target completion: {study_plan.completion_target}"""
                }
            ],
            response_format={"type": "json_object"}
        )

        updated_schedule = json.loads(response.choices[0].message.content)
        study_plan.update_schedule(updated_schedule)
        return True

    except Exception as e:
        logging.error(f"Failed to update study plan: {e}")
        return False