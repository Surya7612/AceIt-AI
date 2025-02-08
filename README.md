```
├── app/
│   ├── app.py                 # Main application file
│   ├── auth.py               # Authentication routes and logic
│   ├── extensions.py         # Flask extensions setup
│   ├── models.py             # Database models
│   ├── ai_helper.py          # AI integration utilities
│   ├── document_processor.py # Document processing utilities
│   └── celery_worker.py      # Background task processing
├── static/                   # Static files (CSS, JS, images)
├── templates/               # HTML templates
│   ├── auth/               # Authentication templates
│   ├── chat.html
│   ├── documents.html
│   ├── folders.html
│   ├── interview_practice.html
│   ├── study_plan.html
│   └── study_plan_view.html
├── instance/               # Instance-specific files
├── main.py                # Application entry point
├── pyproject.toml         # Python dependencies
└── README.md             # Project documentation
```
```

## Tech Stack

- Flask web framework
- SQLAlchemy for database management
- Celery for asynchronous task processing
- Redis for task queue management
- OpenAI GPT-4 integration
- Bootstrap for frontend styling

## Setup Instructions

1. Clone the repository:
```bash
git clone https://github.com/yourusername/aceit-ai.git
cd aceit-ai
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
Create a `.env` file with the following variables:
```
DATABASE_URL=postgresql://...
OPENAI_API_KEY=your_key_here
FLASK_SECRET_KEY=your_secret_key
```

4. Initialize the database:
```bash
flask db upgrade
```

5. Run the application:
```bash
python main.py
```

## Running Development Server

The development server will start on http://localhost:5000

For running with Celery worker:
```bash
# Terminal 1: Run Redis
redis-server

# Terminal 2: Run Celery Worker
celery -A celery_worker worker --loglevel=info

# Terminal 3: Run Flask Application
python main.py
