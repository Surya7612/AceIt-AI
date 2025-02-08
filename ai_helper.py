import os
import json
import logging
from datetime import datetime, timedelta
from extensions import openai_client
from cache_helper import cache_data, get_cached_data
from models import Document, StudyPlan

def generate_study_schedule(topic, priority, daily_time, completion_date, difficulty, goals):
    """Generate an optimized study schedule based on user preferences"""
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4",  # Using standard gpt-4 model
            messages=[
                {
                    "role": "system",
                    "content": """Create an optimized study schedule based on the provided parameters.
                    Return a JSON object with the following structure:
                    {
                        "title": "Study plan title",
                        "daily_sessions": [
                            {
                                "day": "1",
                                "topics": ["Topic 1", "Topic 2"],
                                "duration_minutes": number,
                                "activities": [
                                    {
                                        "type": "study|practice|review",
                                        "topic": "Specific topic",
                                        "duration": number,
                                        "description": "Activity description"
                                    }
                                ]
                            }
                        ],
                        "milestones": [
                            {
                                "day": number,
                                "description": "Milestone description",
                                "assessment": "How to verify completion"
                            }
                        ],
                        "difficulty_level": "beginner|intermediate|advanced",
                        "estimated_completion_days": number,
                        "daily_time_required": number,
                        "prerequisites": ["Prerequisite 1", "Prerequisite 2"],
                        "learning_path": {
                            "phase1": {
                                "focus": "What to focus on",
                                "duration_days": number
                            }
                        }
                    }"""
                },
                {
                    "role": "user",
                    "content": f"""Generate a study schedule with these parameters:
                    Topic: {topic}
                    Priority Level: {priority} (1=High, 2=Medium, 3=Low)
                    Daily Study Time: {daily_time} minutes
                    Target Completion: {completion_date}
                    Difficulty: {difficulty}
                    Goals: {goals}"""
                }
            ],
            response_format={"type": "json_object"}
        )

        schedule = json.loads(response.choices[0].message.content)
        return schedule
    except Exception as e:
        logging.error(f"Failed to generate study schedule: {e}")
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