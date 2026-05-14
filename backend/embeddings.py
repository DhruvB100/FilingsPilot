import os
import time
from openai import OpenAI, RateLimitError

from backend import config  # noqa, loads .env

EMBED_DIMS = 512  # text-embedding-3-small can shrink dims, 512 is plenty and the db stays small
PRICE_PER_1M = 0.02  # USD, text-embedding-3-small

_client = None
tokens_used = 0


def get_client():
    global _client
    if _client is None:
        # the endpoint in .env is the new azure "v1" one so the normal OpenAI client works
        _client = OpenAI(
            base_url=os.getenv("AZURE_OPENAI_ENDPOINT").rstrip("/") + "/",
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        )
    return _client


def embed(texts):
    global tokens_used
    for attempt in range(6):
        try:
            resp = get_client().embeddings.create(
                model=os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT"),
                input=texts,
                dimensions=EMBED_DIMS,
            )
            tokens_used += resp.usage.total_tokens
            return [d.embedding for d in resp.data]
        except RateLimitError:
            wait = 10 * (attempt + 1)
            print(f"  rate limited, sleeping {wait}s")
            time.sleep(wait)
    raise Exception("embedding failed after retries")


def embed_one(text):
    return embed([text])[0]


def cost_so_far():
    return tokens_used / 1_000_000 * PRICE_PER_1M
