# AceIt AI — Intelligent Interview Preparation Platform

**Portfolio stack:** Flask, PostgreSQL, Redis, Celery, OpenAI (chat + embeddings), hybrid **RAG** (BM25 + embeddings + optional expand/rerank), Stripe-ready subscriptions.

| | |
|:--|:--|
| **Live demo** | *Add your public URL after deploying (e.g. `https://aceit-ai.up.railway.app`)* |
| **Source** | *Replace with your GitHub repository URL* |

### Demo path (golden path for reviewers)

1. **Register** and **log in**.  
2. **Upload** a short PDF or paste-friendly doc → wait until it shows **processed** (the **Celery worker** must be running).  
3. Use **study plans** or **chat** and ask something that should be grounded in your uploaded material.

### Before you ship (portfolio checklist)

- [ ] **Railway:** web (Gunicorn) + **worker** (`celery -A celery_worker worker --loglevel=info`) + **Postgres** + **Redis**; on the worker service, **disable HTTP healthcheck** (see [Deploy on Railway](#deploy-on-railway)).  
- [ ] **`uploads/`:** attach a [volume](https://docs.railway.app/guides/volumes) at `uploads` or accept that files reset on redeploy.  
- [ ] **Secrets:** set **`OPENAI_API_KEY`** and a strong **`FLASK_SECRET_KEY`** in the platform UI only; use **`SESSION_COOKIE_SECURE=true`** behind HTTPS.  
- [ ] **OpenAI spend:** set an account budget alert; optional env caps — **`RAG_QUERY_EXPAND=false`**, **`RAG_LLM_RERANK=false`**, lower **`RAG_EMBEDDING_POOL`** (see `.env.example`).  
- [ ] **Stripe:** use **test mode** for demos, or omit keys until webhooks are configured.  
- [ ] **README:** replace the **Live demo** and **Source** placeholders above with real links.

Environment template: copy **`.env.example`** → **`.env`** (see [Environment Configuration](#3-environment-configuration)).

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

#### Deploy on Railway

Use three pieces: **web** (Gunicorn), **worker** (Celery), and managed **PostgreSQL** + **Redis**. The repo **`Procfile`** defines:

- **`release`** — runs **`flask db upgrade`** before each deploy (set **`FLASK_APP=main:app`** in the service variables, or rely on **`.flaskenv`** if your build copies it).
- **`web`** — **`gunicorn "app:app"`** bound to **`$PORT`** (Railway injects **`PORT`** automatically).
- **`worker`** — **not** started by the web service; create a **second Railway service** from the same repo and set the start command to:  
  **`celery -A celery_worker worker --loglevel=info`**  
  On that worker service, **disable the HTTP healthcheck** in Railway (there is no `/health` listener); **`railway.json`** is intended for the **web** process only.

**Variables (web + worker):** mirror your `.env`: **`DATABASE_URL`** (from Railway Postgres; the app normalizes legacy **`postgres://`** URLs), **`REDIS_URL`** (Railway Redis plugin), **`OPENAI_API_KEY`**, **`FLASK_SECRET_KEY`**, and for HTTPS **`SESSION_COOKIE_SECURE=true`**.

**`nixpacks.toml`** installs **`tesseract-ocr`** so image OCR works on Railway’s build image.

**`railway.json`** sets **`deploy.healthcheckPath`** to **`/health`** (see **`health.py`**) so deploys wait for a **`200`** from Gunicorn before traffic shifts.

**Uploads:** the default **`uploads/`** folder is on ephemeral disk unless you attach a [Railway volume](https://docs.railway.app/guides/volumes) mounted at **`uploads`** (or switch to object storage later).

Official docs: [Railway](https://docs.railway.app/).

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
├── health.py            # /health for load balancers (Railway healthcheck)
├── ai_helper.py         # LLM / tutor helpers
├── rag_context.py       # BM25 + hybrid retrieval orchestration
├── rag_embeddings.py    # Embeddings + fusion
├── celery_worker.py     # Celery tasks (document pipeline)
├── migrations/          # Alembic revisions
├── static/              # Static assets
├── templates/           # Jinja templates
├── tests/               # Pytest suite
└── uploads/             # User uploads (use a volume in production)
```
