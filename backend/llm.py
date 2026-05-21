"""
One place to pick the LLM. LLM_PROVIDER=azure (default) or gemini.
Gemini is only for the model comparison eval - it costs real money on my GCP account, don't use it for dev.
"""
import os
from backend import config  # noqa, loads .env

# USD per 1M tokens (input, output)
PRICES = {
    "azure": (0.25, 2.00),   # gpt-5-mini
    "gemini": (0.30, 2.50),  # gemini-2.5-flash
}


def get_llm(provider=None, max_tokens=2000):
    provider = provider or os.getenv("LLM_PROVIDER", "azure")

    if provider == "azure":
        from langchain_openai import ChatOpenAI
        # azure "v1" endpoint works with the normal openai client, model = deployment name
        # gpt-5-mini is a reasoning model, no temperature. low effort keeps it cheap
        return ChatOpenAI(
            base_url=os.getenv("AZURE_OPENAI_ENDPOINT").rstrip("/") + "/",
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            model=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT"),
            reasoning_effort="low",
            max_tokens=max_tokens,
            timeout=90,
            max_retries=3,
        )

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        # vertexai=True -> goes through GCP (Agent Platform API) with the service account in secrets/
        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            vertexai=True,
            project=os.getenv("GCP_PROJECT_ID"),
            location=os.getenv("GCP_LOCATION", "us-central1"),
            max_output_tokens=max_tokens,
            thinking_budget=512,
            temperature=0,
        )

    raise ValueError("unknown LLM_PROVIDER " + provider)


def cost(provider, input_tokens, output_tokens):
    p_in, p_out = PRICES.get(provider or os.getenv("LLM_PROVIDER", "azure"), (0, 0))
    return input_tokens / 1_000_000 * p_in + output_tokens / 1_000_000 * p_out
