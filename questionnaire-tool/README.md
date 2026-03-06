# ALMABASE Structured Questionnaire Tool

This project is my take-home assignment for the GTM Engineering Internship.

It helps teams answer structured questionnaires (like security or compliance forms) using internal reference documents.

## What this app does

- User signup, login, logout
- Upload reference documents
- Upload a questionnaire file
- Generate answers using AI
- Add citations for each supported answer
- Return `Not found in references.` when answer is not supported
- Review and edit answers before final export
- Export answered file (CSV/XLSX)

## Fictional company and industry

- Industry: Fintech SaaS
- Fictional company: **AlmaLedger**
- AlmaLedger helps small and medium businesses automate bookkeeping and spend controls.
- It follows SOC2-style controls and role-based access.

See: `sample_data/fictional_company.md`

## Sample files included

- Questionnaire: `sample_data/questionnaire.csv`
- References:
  - `sample_data/reference_01_security_policy.txt`
  - `sample_data/reference_02_incident_response.txt`
  - `sample_data/reference_03_privacy_and_data.txt`
  - `sample_data/reference_04_business_continuity.txt`

## Simple user flow

1. Sign up or log in
2. Upload reference docs
3. Upload questionnaire
4. Click Generate answers
5. Review answers + citations
6. Edit if needed
7. Export final file

## Tech stack

- Backend: FastAPI
- UI: Jinja templates
- Database: SQLite (`data/app.db`)
- ORM: SQLAlchemy
- AI: OpenAI API (if key is provided)
- Fallback AI: local heuristic when API key is missing

## Must-have requirement checklist

- Authentication: yes
- Persistent database: yes
- Upload to export flow: yes
- AI does meaningful work: yes
- Answers grounded with citations: yes
- Unsupported answers return `Not found in references.`: yes

## Nice-to-have features implemented

- Confidence score
- Evidence snippets
- Partial regeneration (selected questions only)
- Coverage summary (total, answered with citations, not found)

## Assumptions

- Best experience is with CSV/XLSX questionnaires
- PDF parsing is basic text extraction
- Citations are shown at source chunk level (`filename#chunk-id`)

## Trade-offs

- Retrieval is lightweight lexical matching (faster and simpler)
- Export is practical table format (not pixel-perfect PDF reconstruction)
- Auth is simple session-based login

## If I had more time

- Better retrieval with embeddings + reranking
- Better PDF structure parsing
- Full version history and run comparison
- Sentence-level citation highlights
- Production security improvements

## Local setup

1. Create virtual environment
2. Install packages:

```bash
pip install -r requirements.txt
```

3. Create env file:

```bash
copy .env.example .env
```

4. Set values in `.env`:

- `APP_SECRET` = random secure string
- `OPENAI_API_KEY` = optional
- `OPENAI_MODEL` = optional (default: `gpt-4.1-mini`)

5. Run FastAPI app:

```bash
python -m uvicorn app.main:app --reload
```

6. Open:

`http://127.0.0.1:8000`

## Deploy to Railway

In Railway, create a new project from your GitHub repo and set:

- Root Directory: `questionnaire-tool`
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Environment variables:

- `APP_SECRET` = long random string
- `OPENAI_API_KEY` = optional
- `OPENAI_MODEL` = optional (`gpt-4.1-mini`)

For persistent DB on Railway:

1. Add a PostgreSQL service in the same Railway project.
2. Railway provides `DATABASE_URL` automatically.
3. This app will use `DATABASE_URL` if present, otherwise local SQLite.

## Final submission items

- Live app link
- GitHub repository link
- This README
