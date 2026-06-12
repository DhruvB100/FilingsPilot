"""
One place to pick the LLM. LLM_PROVIDER=azure (default) or gemini.
Gemini is only for the model comparison eval - it costs real money on my GCP account, don't use it for dev.
"""
import os
from backend import config  # noqa: F401  (loads .env)

# USD per 1M tokens (input, output)
PRICES = {
    "azure": (0.25, 2.00),   # gpt-5-mini
    "gemini": (0.50, 3.00),  # gemini-3-flash-preview
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
            stream_usage=True,  # without this token usage is missing when streaming -> cost shows $0
            timeout=90,
            max_retries=3,
        )

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        # vertexai=True -> goes through GCP (Agent Platform API) with the service account in secrets/
        # gemini-2.5-flash gives 404 on my (new) project, 3-flash-preview only works in the "global" location
        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"),
            vertexai=True,
            project=os.getenv("GCP_PROJECT_ID"),
            location=os.getenv("GCP_LOCATION", "global"),
            max_output_tokens=max_tokens,
            thinking_config={"thinking_level": "low"},
        )

    raise ValueError("unknown LLM_PROVIDER " + provider)


def cost(provider, input_tokens, output_tokens):
    p_in, p_out = PRICES.get(provider or os.getenv("LLM_PROVIDER", "azure"), (0, 0))
    return input_tokens / 1_000_000 * p_in + output_tokens / 1_000_000 * p_out
