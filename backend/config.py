import os
from dotenv import load_dotenv

load_dotenv()

EDGAR_USER_AGENT = os.getenv("EDGAR_USER_AGENT", "")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://filings:filings@localhost:5432/filings")

DATA_DIR = os.getenv("DATA_DIR", "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
FACTS_DIR = os.path.join(DATA_DIR, "facts")

# how many annual reports per company we keep (more = more embedding cost)
YEARS_TO_KEEP = int(os.getenv("YEARS_TO_KEEP", "2"))
