import os
import json
import logging
from datetime import datetime, timedelta
from extensions import openai_client
from cache_helper import cache_data, get_cached_data
from models import Document, StudyPlan

def generate_study_schedule(topic, priority, daily_time, completion_date, difficulty, goals, documents=None, link=None):
    """Generate an optimized study schedule based on user preferences and optional documents"""
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

        system_message = """You are an expert study plan creator specializing in interview preparation. 
Create a comprehensive study plan that includes:
1. A detailed summary of the topic and learning objectives
2. Key concepts that need to be mastered
3. A structured learning path divided into sections
4. Practice questions with detailed explanations
5. Additional resources and references

Format the response as a JSON object with the following structure:
{
    "title": "Topic name",
    "summary": "Comprehensive overview",
    "difficulty_level": "beginner/intermediate/advanced",
    "estimated_total_hours": number,
    "key_concepts": [
        {
            "name": "Concept name",
            "description": "Detailed explanation",
            "priority": "high/medium/low"
        }
    ],
    "learning_path": [
        {
            "day": number,
            "duration_minutes": number,
            "topics": ["Topic 1", "Topic 2"],
            "activities": [
                {
                    "type": "study/practice/review",
                    "description": "Activity description",
                    "duration_minutes": number
                }
            ]
        }
    ],
    "sections": [
        {
            "title": "Section name",
            "content": "Detailed content",
            "key_points": ["Point 1", "Point 2"],
            "examples": ["Example 1", "Example 2"]
        }
    ],
    "practice_questions": [
        {
            "question": "Question text",
            "answer": "Detailed answer",
            "explanation": "Conceptual explanation",
            "difficulty": "easy/medium/hard",
            "category": "technical/behavioral/system design"
        }
    ],
    "additional_resources": [
        {
            "title": "Resource name",
            "type": "article/video/tutorial",
            "description": "Brief description",
            "url": "Optional URL"
        }
    ]
}"""

        # Calculate study duration in days
        target_date = datetime.strptime(completion_date, '%Y-%m-%d')
        days_until_target = (target_date - datetime.now()).days

        study_request = f"""Create a detailed study plan with these parameters:
Topic: {topic}
Priority Level: {priority} (1=High, 2=Medium, 3=Low)
Daily Study Time: {daily_time} minutes
Days until completion: {days_until_target} days
Target Completion: {completion_date}
Difficulty Level: {difficulty}
Learning Goals: {goals}

Requirements:
1. Plan should be completable within {days_until_target} days with {daily_time} minutes per day
2. Difficulty should match specified level: {difficulty}
3. Content should be specifically tailored for {topic} interview preparation
4. Include a mix of theoretical concepts and practical examples
5. Add practice questions that test different aspects of the topic
6. Recommend additional resources for deeper learning"""

        if has_materials:
            study_request += f"\nUse this additional context to customize the plan:\n{context}"

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": study_request}
        ]

        logging.info("Generating study plan with OpenAI")
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7,
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content
        schedule = json.loads(content)
        logging.debug(f"Generated content: {json.dumps(schedule, indent=2)}")

        return schedule

    except Exception as e:
        logging.error(f"Failed to generate study schedule: {str(e)}")
        raise Exception(f"Failed to generate study schedule: {str(e)}")

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