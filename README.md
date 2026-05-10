# AceIt AI — Intelligent Interview Preparation Platform

## Product Description:
AceIt AI is an innovative interview preparation platform that leverages artificial intelligence to help job seekers improve their interview skills through personalized learning and real-time feedback. The platform combines advanced AI technologies with interactive learning tools to create a comprehensive interview preparation experience.

## Key Features:

#### Personalized Study Plans

- AI-generated study schedules based on user goals
- Progress tracking and adaptive learning paths
- Resource organization with folders and document management
- Interactive Interview Practice

#### AI-generated interview questions based on job descriptions

- Real-time feedback on responses
- Support for text, audio, and video responses
- Confidence scoring and performance analytics
- Smart Document Management

#### Document upload and organization
- AI-powered content extraction and summarization
- Structured content categorization
- AI-Powered Chat Assistance

#### Context-aware tutoring
- Real-time question answering
- Interview strategy guidance

## Technical Stack:

#### Backend Infrastructure:

- Flask web framework
- SQLAlchemy ORM
- PostgreSQL database
- Alembic migrations via Flask-Migrate
- Redis for caching
- Celery for background tasks

#### AI Integration:

- OpenAI GPT-4 for content generation
- Whisper API for speech-to-text
- Custom AI models for analysis

#### Security:

- Session-based authentication (Flask-Login)
- Role-based access control
- Secure file handling
- Environment-based configuration

### Installation Requirements:

#### System Requirements:

- Python 3.11+
- PostgreSQL 12+
- Redis Server
- Modern web browser

Either **`pip install -r requirements.txt`** or **`uv sync`** using **`pyproject.toml`** / **`uv.lock`**.

#### Key Dependencies:

- Flask and extensions (SQLAlchemy, Login, WTF, Migrate)
- Celery for async tasks
- OpenAI API
- Email validation
- Secure password hashing

#### Environment Variables:

- Database configuration
- OpenAI API credentials
- Flask security keys
- Server configuration

#### Development Setup:

- Initialize PostgreSQL database
- Configure Redis server
- Set up Celery worker
- Configure environment variables
- Initialize Flask application

### In Details:

### 1. Clone Repository
```
git clone https://github.com/yourusername/aceit-ai.git
cd aceit-ai
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Configuration

Copy the tracked template and edit locally (never commit secrets):

```bash
cp .env.example .env
```

All variables are documented with defaults in **`.env.example`**. Minimum for production-shaped deploys:

```env
DATABASE_URL=postgresql://username:password@host:port/database
REDIS_URL=redis://...
OPENAI_API_KEY=your_openai_api_key
FLASK_SECRET_KEY=your_secret_key_here
FLASK_APP=main:app
SESSION_COOKIE_SECURE=true
```

#### Retrieval / RAG (optional)

Hybrid retrieval mixes **BM25** (lexical) with **OpenAI embeddings**. Candidate vectors are cached in **Redis** when `REDIS_URL` is set; **`chunk_embedding_cache`** (SQL, migration **`002_chunk_embedding_cache`**) survives Redis eviction. pytest defaults **`RAG_USE_EMBEDDINGS=false`**, **`RAG_QUERY_EXPAND=false`**, and **`RAG_LLM_RERANK=false`** so tests stay offline-friendly—production usually enables embeddings.

| Variable | Default | Purpose |
|----------|---------|---------|
| `RAG_USE_EMBEDDINGS` | `true` | `true` / `1` / `yes`: BM25 + embedding fusion; `false`: lexical BM25 only. |
| `RAG_HYBRID_LEX_WEIGHT` | `0.35` | Weight for normalized BM25 in the fused score (remainder goes to embedding similarity). |
| `RAG_EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model id. |
| `RAG_EMBEDDING_POOL` | `48` | Max chunks scored with embeddings after BM25 shortlist. |
| `RAG_EMBEDDING_CACHE_TTL` | `604800` (7 days) | Redis TTL for embedding payloads (seconds). |
| `RAG_EMBEDDING_MAX_CHARS` | `6000` | Truncate chunk text before hashing / embedding. |
| `RAG_QUERY_EXPAND` | `false` | When enabled, adds synonym-style phrases via chat (`RAG_EXPAND_MODEL`, default `gpt-4o-mini`). |
| `RAG_EXPAND_MODEL` | `gpt-4o-mini` | Model for query expansion JSON. |
| `RAG_LLM_RERANK` | `false` | When enabled, reranks the top fused candidates (`RAG_RERANK_MODEL`, `RAG_RERANK_POOL`). |
| `RAG_RERANK_MODEL` | `gpt-4o-mini` | Model for permutation rerank JSON. |
| `RAG_RERANK_POOL` | `12` | How many top fused chunks the reranker may reorder. |

#### Deploy on Replit

Configured via **`.replit`** (Run workflows + published deployment) and **`replit.nix`** (Redis, Tesseract OCR, PostgreSQL client tooling, OpenSSL).

**1. Secrets** (Tools → **Secrets** — mirror **`.env.example`**):

- **`DATABASE_URL`** — Replit PostgreSQL or any hosted Postgres (`postgres://` is normalized for SQLAlchemy).
- **`REDIS_URL`** — dev: `redis://127.0.0.1:6379/0` with the **Redis Server** workflow. Published Autoscale runs **only** the deployment command (Gunicorn), so use **hosted Redis** for production-shaped URLs unless your Replit plan runs Redis/workers alongside the deployment.
- **`OPENAI_API_KEY`**, **`FLASK_SECRET_KEY`**, **`FLASK_APP=main:app`**
- **`SESSION_COOKIE_SECURE=true`** on HTTPS Replit hosts.

**2. Shell (once per fresh database):**

```bash
pip install -r requirements.txt
flask db upgrade
```

**3. Development Run** — **Run** → **Project** starts **Flask Server** (Gunicorn, port **5000**), **Celery Worker**, and **Redis Server** in parallel.

**4. Published deployment** — **`[deployment]`** in **`.replit`** targets Autoscale: **`gunicorn 'app:app'`** on **`0.0.0.0:$PORT`**. Background document processing still requires **Celery** connected to the same **`REDIS_URL`** as the web app—follow [Replit deployment docs](https://docs.replit.com/hosting/deployments/about-deployments) for workers / Always-On patterns on your plan.

**5. Health:** HTTP GET `/health` returns `{"status":"ok"}`.

**Uploads** live under **`uploads/`**; treat as ephemeral across repl resets.

**Optional:** **`Procfile`** helps Heroku-style hosts only; Replit uses **`.replit`** for the publish command.

### 4. Database Initialization

Uses **[Flask-Migrate](https://flask-migrate.readthedocs.io/)** (Alembic). With **`FLASK_APP`** set (see **`.flaskenv`** or **`export FLASK_APP=main:app`**):

```bash
flask db upgrade
```

Revisions include **`001_baseline`** (core schema; skips DDL when tables already exist for databases previously created with `create_all`) and **`002_chunk_embedding_cache`** (embedding vector persistence). New environments apply the full chain via **`flask db upgrade`**. After changing models, generate migrations with **`flask db migrate -m "message"`**.

### 5. Start Services
```bash
# Start Redis server (required for Celery)
redis-server

# Start Celery worker
celery -A celery_worker worker --loglevel=info

# Start Flask application
python main.py
```

## AI Integration

### OpenAI GPT-4 Integration
The platform uses OpenAI's GPT-4 model for various features:
- Interview question generation
- Answer analysis and feedback
- Study plan creation
- Document summarization
- Interactive chat assistance

### Audio Processing
- Whisper API for speech-to-text
- Real-time transcription
- Audio analysis for confidence scoring

## Project Structure
```
├── app.py               # Routes and HTTP handlers
├── auth.py              # Authentication blueprint
├── subscription.py      # Stripe subscription blueprint
├── extensions.py        # Flask app, SQLAlchemy, login, CSRF, migrations
├── models.py            # ORM models
├── health.py            # GET /health for uptime probes
├── .replit              # Replit workflows & deployment command
├── replit.nix           # Replit Nix deps (redis, tesseract, postgres, openssl)
├── ai_helper.py         # LLM / tutor helpers
├── rag_context.py       # BM25 + hybrid retrieval orchestration
├── rag_embeddings.py    # Embeddings + fusion
├── celery_worker.py     # Celery tasks (document pipeline)
├── migrations/          # Alembic revisions
├── static/              # Static assets
├── templates/           # Jinja templates
├── tests/               # Pytest suite
└── uploads/             # User uploads (ephemeral on Repl unless you sync out)
```
