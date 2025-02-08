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

        # Convert priority to intensity level and detailed requirements
        priority_details = {
            1: {
                "intensity": "high intensity, comprehensive coverage",
                "depth": "in-depth coverage of both fundamental and advanced concepts",
                "practice": "extensive practice with complex scenarios",
                "time_allocation": "60% core concepts, 40% advanced topics"
            },
            2: {
                "intensity": "medium intensity, balanced coverage",
                "depth": "solid understanding of fundamentals with selected advanced topics",
                "practice": "balanced practice with mixed difficulty levels",
                "time_allocation": "70% core concepts, 30% advanced topics"
            },
            3: {
                "intensity": "focused intensity, essential coverage",
                "depth": "strong grasp of fundamental concepts",
                "practice": "focused practice on essential skills",
                "time_allocation": "85% core concepts, 15% advanced topics"
            }
        }

        priority_info = priority_details.get(int(priority))
        intensity = priority_info["intensity"]

        messages = [
            {
                "role": "system",
                "content": f"""You are an expert study plan creator specializing in interview preparation. 
Create a comprehensive study plan following these exact requirements:

1. Content depth and coverage:
   - Intensity: {priority_info["intensity"]}
   - Depth: {priority_info["depth"]}
   - Practice focus: {priority_info["practice"]}
   - Time allocation: {priority_info["time_allocation"]}

2. Your output MUST be a valid JSON string with this exact structure:
{{
    "title": "{topic}",
    "summary": "A detailed overview explaining the approach and key focus areas",
    "difficulty_level": "{difficulty}",
    "estimated_total_hours": number,
    "priority_level": "{intensity}",
    "key_concepts": [
        {{
            "name": "string",
            "description": "Detailed concept explanation with examples",
            "priority": "high/medium/low",
            "estimated_time": number
        }}
    ],
    "learning_path": [
        {{
            "day": number,
            "duration_minutes": {daily_time},
            "topics": ["Specific topics covered"],
            "activities": [
                {{
                    "type": "study/practice/review/assessment",
                    "description": "Detailed activity description",
                    "duration_minutes": number,
                    "priority": "high/medium/low"
                }}
            ]
        }}
    ],
    "sections": [
        {{
            "title": "Section title",
            "content": "Comprehensive content with clear explanations",
            "key_points": ["Specific key points"],
            "examples": ["Detailed examples"],
            "priority": "high/medium/low",
            "recommended_time": number
        }}
    ],
    "practice_questions": [
        {{
            "question": "Clear, specific question",
            "answer": "Detailed answer with explanations",
            "explanation": "Concept explanation and approach",
            "difficulty": "easy/medium/hard",
            "category": "Category name",
            "priority": "high/medium/low"
        }}
    ],
    "additional_resources": [
        {{
            "title": "Resource name",
            "type": "article/video/tutorial/documentation",
            "description": "What to focus on in this resource",
            "url": "URL if available",
            "priority": "high/medium/low"
        }}
    ]
}}

3. Content requirements:
   - All JSON fields must be present and properly formatted
   - All number values must be actual numbers, not strings
   - Use consistent priority values: "high", "medium", "low"
   - Use consistent difficulty values: "easy", "medium", "hard"
   - All arrays must have multiple items
   - Include detailed explanations and examples
   - Ensure time estimates are realistic and sum up correctly"""
            },
            {
                "role": "user",
                "content": f"""Create a detailed study plan with these parameters:
Topic: {topic}
Priority Level: {priority} (1=High, 2=Medium, 3=Low)
Daily Study Time: {daily_time} minutes
Days until completion: {days_until_target} days
Target Completion: {completion_date}
Difficulty Level: {difficulty}
Learning Goals: {goals}

Requirements:
1. Plan MUST be completable in {days_until_target} days with {daily_time} minutes daily sessions
2. Match difficulty level: {difficulty}
3. Content must be specifically tailored for {topic} interview preparation
4. Structure content based on priority level {priority}:
   - High (1): Comprehensive coverage with advanced topics, complex examples, and extensive practice
   - Medium (2): Balanced coverage with mix of fundamental and advanced topics
   - Low (3): Focus on core concepts with clear examples and essential practice
5. Break down daily activities into focused segments within {daily_time} minutes
6. Include varied practice questions matching difficulty and priority
7. Ensure realistic time estimates for each activity"""
            }
        ]

        if has_materials:
            messages[1]["content"] += f"\nIncorporate this additional context:\n{context}"

        logging.info("Generating study plan with OpenAI")
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7,
            max_tokens=3000  # Increased token limit for more detailed content
        )

        # Parse and validate the response
        try:
            content = response.choices[0].message.content
            schedule = json.loads(content)

            # Enhanced validation
            required_fields = ["title", "summary", "difficulty_level", "estimated_total_hours", 
                             "key_concepts", "learning_path", "sections", "practice_questions"]

            if not all(field in schedule for field in required_fields):
                raise ValueError("Missing required fields in generated schedule")

            # Validate content length and detail level
            if len(schedule["key_concepts"]) < 3:
                raise ValueError("Insufficient key concepts")
            if len(schedule["sections"]) < 3:
                raise ValueError("Insufficient content sections")
            if len(schedule["practice_questions"]) < 5:
                raise ValueError("Insufficient practice questions")

            logging.debug(f"Generated study plan: {json.dumps(schedule, indent=2)}")
            return schedule

        except json.JSONDecodeError as je:
            logging.error(f"Failed to parse OpenAI response as JSON: {str(je)}\nContent: {content}")
            raise Exception("Failed to generate valid study schedule format")
        except Exception as e:
            logging.error(f"Error validating study schedule: {str(e)}")
            raise Exception(f"Failed to validate study schedule: {str(e)}")

    except Exception as e:
        logging.error(f"Failed to generate study schedule: {str(e)}")
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