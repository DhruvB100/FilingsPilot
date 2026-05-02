# the 10 canadian companies that also file with the SEC
# CIKs looked up from https://www.sec.gov/files/company_tickers.json
COMPANIES = [
    {"ticker": "CVE", "name": "Cenovus Energy", "cik": 1475260, "sector": "Energy"},
    {"ticker": "SU", "name": "Suncor Energy", "cik": 311337, "sector": "Energy"},
    {"ticker": "TRP", "name": "TC Energy", "cik": 1232384, "sector": "Energy"},
    {"ticker": "ENB", "name": "Enbridge", "cik": 895728, "sector": "Energy"},
    {"ticker": "CNQ", "name": "Canadian Natural Resources", "cik": 1017413, "sector": "Energy"},
    {"ticker": "RY", "name": "Royal Bank of Canada", "cik": 1000275, "sector": "Banking"},
    {"ticker": "TD", "name": "Toronto-Dominion Bank", "cik": 947263, "sector": "Banking"},
    {"ticker": "BMO", "name": "Bank of Montreal", "cik": 927971, "sector": "Banking"},
    {"ticker": "CM", "name": "CIBC", "cik": 1045520, "sector": "Banking"},
    {"ticker": "SHOP", "name": "Shopify", "cik": 1594805, "sector": "Technology"},
]


def get_company(ticker):
    for c in COMPANIES:
        if c["ticker"] == ticker.upper():
            return c
    return None
