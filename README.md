# FilingsPilot

AI agent that answers questions about Canadian public companies using their SEC filings (40-F / 10-K).
It searches the annual reports (hybrid RAG), queries the financial numbers with SQL, cites every source,
and opens a Jira ticket when the text and the numbers disagree.

Work in progress.

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # fill it in
docker compose up -d
```

## Load the data

```
python -m backend.edgar          # download filings + company facts from SEC EDGAR
python -m backend.chunker        # split into chunks
python -m backend.db             # create tables
python -m backend.index_filings  # embed + load chunks (costs ~$0.07 in embeddings)
python -m backend.load_facts     # load the numbers
```

## Ask something

```
python -m backend.agent "How did Cenovus revenue change from 2024 to 2025 and why?"
uvicorn backend.api:app --reload   # POST /chat streams the answer (SSE)
```
