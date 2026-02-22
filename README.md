# TalentCopilot

Multi-tenant, memory-enabled chatbot for recruiting teams, with **Human-in-the-Loop (HITL)** confirmation for tool actions. Built with FastAPI, LangChain, LangGraph, PostgreSQL, and Streamlit.

## Features

- **Conversational chat** about candidates and repositories
- **GitHub repo ingestion** (HITL-gated): agent asks "Would you like me to crawl this repository: &lt;url&gt;? (yes/no)" before ingesting
- **CV parsing** (PDF/DOCX) and **save to workspace** (HITL-gated): agent asks "Do you want me to save this candidate profile to the workspace? (yes/no)"
- **Persisted memory** per tenant/user/session (recent messages + session summary + workspace artifacts)
- **Multi-tenant isolation** enforced at DB and API layer
- **Job-based** non-blocking GitHub ingestion; poll `GET /jobs/{job_id}` for status

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy (async), PostgreSQL (asyncpg)
- **AI**: LangChain, LangGraph, OpenAI
- **Frontend**: Streamlit

## Prerequisites

- Python 3.10+
- PostgreSQL 14+
- OpenAI API key

## Setup

### 1. Clone and install

```bash
cd talentcopilot
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

### 2. Environment

Copy `.env.example` to `.env` and set:

```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/talentcopilot
OPENAI_API_KEY=sk-your-openai-key
# Optional: GITHUB_TOKEN for higher GitHub API rate limits
```

### 3. Create PostgreSQL database

```bash
createdb talentcopilot
```

(or create via pgAdmin / your DB tool). Tables are created automatically on first API startup.

#### Connecting to your local PostgreSQL database

The app uses **PostgreSQL only** (via the **asyncpg** driver and SQLAlchemy `postgresql+asyncpg://` URLs). No SQLite.

**Connection string format:**

```
postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DATABASE
```

Example for local:

- `postgresql+asyncpg://postgres:postgres@localhost:5432/talentcopilot`

Set this in `.env` as `DATABASE_URL`; the backend reads it at startup.

**Ways to connect to local PostgreSQL (for inspection, debugging, or creating the DB):**

| Tool | Use case |
|------|----------|
| **psql** | Command-line client. Example: `psql -U postgres -d talentcopilot -h localhost -p 5432` |
| **pgAdmin** | Free GUI (https://www.pgadmin.org/). Add server: host `localhost`, port `5432`, user/password, then open database `talentcopilot`. |
| **DBeaver** | Free universal DB GUI. New connection → PostgreSQL → localhost:5432, database `talentcopilot`. |
| **VS Code** | Extension “PostgreSQL” by Chris Kolkman: connect with host, port, user, password, database name. |
| **Azure Data Studio** | With “PostgreSQL” extension: connect to `localhost`, database `talentcopilot`. |

Replace `USER`/`PASSWORD` with your local PostgreSQL user (e.g. `postgres` / your password). Default port is `5432`.

### 4. Run backend

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or from project root:

```bash
python -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Run frontend

In another terminal:

```bash
cd frontend
streamlit run streamlit_app.py
```

Set `TALENTCOPILOT_API_URL=http://localhost:8000` if the API is not on that URL.

## API Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/chat` | Send message; returns assistant reply or HITL confirmation prompt |
| POST | `/confirm` | Send yes/no for a pending confirmation |
| POST | `/upload/cv` | Upload PDF/DOCX; returns parsed profile + confirmation to save |
| GET | `/jobs/{job_id}` | Job status (queued / running / succeeded / failed) |
| GET | `/workspace` | Current tenant/user workspace (candidates + repos) |

All endpoints that need tenant scope expect headers:

- `X-Tenant-ID`
- `X-User-ID`
- `X-Session-ID` (for chat, confirm, upload/cv)

## Example Flows

### 1. CV upload → parse → approve save

1. In the Streamlit sidebar, upload a PDF or DOCX CV.
2. Click **Parse & ask to save**. The app shows: "Do you want me to save this candidate profile to the workspace? (yes/no)".
3. Click **Yes** to persist the candidate to the workspace; **No** to skip.
4. Ask in chat: "What skills does the candidate have?" — the assistant uses workspace context.

### 2. GitHub URL → confirmation → ingestion job

1. In chat, paste a public GitHub repo URL and ask to use it (e.g. "Please ingest https://github.com/owner/repo").
2. The agent replies with: "Would you like me to crawl this repository: https://github.com/owner/repo ? (yes/no)".
3. Click **Yes** in the confirmation UI. A job is created and runs in the background.
4. In the sidebar, job status is shown; poll until status is `succeeded`.
5. Ask in chat: "What's in the README?" or "What's the tech stack?" — the assistant uses ingested repo artifacts.

### 3. Deny GitHub confirmation

1. Paste a GitHub URL and request ingestion.
2. When the confirmation prompt appears, click **No**. No ingestion occurs; chat continues normally.

### 4. Tenant isolation

1. Note the **Tenant ID** and **User ID** in the sidebar (or set them to fixed values).
2. Under Tenant A: upload a CV and save; ingest a repo.
3. Change **Tenant ID** to a different value (Tenant B). Refresh workspace — you should not see Tenant A's candidates or repos.
4. Sessions and data are isolated by `tenant_id` and `user_id`.

## Project Structure

```
talentcopilot/
├── backend/
│   └── app/
│       ├── main.py           # FastAPI app
│       ├── config.py
│       ├── database.py
│       ├── models/          # SQLAlchemy (Tenant, User, Session, Message, etc.)
│       ├── schemas/         # Pydantic request/response
│       ├── repositories/    # Data access with tenant isolation
│       ├── services/        # Agent, memory, CV parser, GitHub ingest
│       ├── api/routes/      # chat, confirm, upload, jobs, workspace
│       ├── core/            # Tenant context
│       └── jobs.py          # Background GitHub ingestion
├── frontend/
│   └── streamlit_app.py    # Chat UI, HITL confirmations, CV upload, job status
├── requirements.txt
├── .env.example
└── README.md
```

## License

MIT (or as specified by your organization).
