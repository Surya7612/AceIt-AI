import os
from openai import OpenAI

# the newest OpenAI model is "gpt-4o" which was released May 13, 2024
# do not change this unless explicitly requested by the user
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai = OpenAI(api_key=OPENAI_API_KEY)

def generate_study_plan(content):
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "Create a detailed study plan based on the provided content. Include sections, goals, and estimated time requirements."
                },
                {"role": "user", "content": content}
            ],
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content
    except Exception as e:
        raise Exception(f"Failed to generate study plan: {e}")

def chat_response(message, context=""):
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful study assistant. Provide clear, concise answers to help students understand concepts better."
                },
                {"role": "user", "content": f"Context: {context}\nQuestion: {message}"}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        raise Exception(f"Failed to generate chat response: {e}")
