# FilingsPilot

AI agent that answers questions about Canadian public companies using their SEC filings (40-F / 10-K).

Work in progress.

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # fill it in
docker compose up -d
```

## Download filings

```
python -m backend.edgar
```
