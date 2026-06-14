"""
Scorers for the eval suite. Each returns a float 0-1, or None when it doesn't apply to that question.
"""
import re
from pydantic import BaseModel, Field

from backend.search import hybrid_search

SCALES = {"trillion": 1e12, "billion": 1e9, "bn": 1e9, "b": 1e9, "million": 1e6, "m": 1e6, "thousand": 1e3, "k": 1e3}
NUM = re.compile(r"(\d[\d,]*\.?\d*)\s*(trillion|billion|million|thousand|bn|b|m|k)?\b", re.I)

# careful with these, "decline" used to be in here and matched "revenue declined" -> correct answers
# got treated as refusals and skipped the faithfulness judge
REFUSAL_PHRASES = ["couldn't find", "could not find", "can't answer", "cannot answer", "not able to answer", "unable to answer",
                   "only answer questions", "can only answer", "i must decline", "i'll have to decline", "can't help with",
                   "cannot help with", "can't provide", "cannot provide", "can't give", "cannot give", "can't tell you",
                   "only allowed to", "not in the filings", "outside what i can"]


def extract_numbers(text):
    text = text.replace(" ", " ")
    # ranges like "C$6.0 to C$6.5 billion" or "$6.0-6.5 billion": the scale word only comes after the
    # second number, so copy it to the first one (this was scoring a correct answer as wrong)
    text = re.sub(r"(\d[\d,]*\.?\d*)(\s*(?:to|-|–)\s*(?:C\$|US\$|\$)?\s*\d[\d,]*\.?\d*\s*(trillion|billion|million))",
                  r"\1 \3\2", text, flags=re.I)
    nums = []
    for value, scale in NUM.findall(text):
        try:
            n = float(value.replace(",", ""))
        except ValueError:
            continue
        if scale:
            n *= SCALES[scale.lower()]
        nums.append(n)
    return nums


def close_enough(found, expected):
    found, expected = abs(found), abs(expected)  # "decreased 8.4%" vs -8.44, sign is in the words
    tolerance = max(expected * 0.01, 0.06 if expected < 100 else 0)
    return abs(found - expected) <= tolerance


def is_refusal(answer):
    a = answer.lower().replace("’", "'")
    return any(p in a for p in REFUSAL_PHRASES)


def answer_correctness(item, result):
    answer = result["answer"]
    if item.get("should_refuse"):
        return 1.0 if is_refusal(answer) else 0.0
    nums = extract_numbers(answer)
    # every group must be matched, a group is a list of acceptable values (like 834.2 or 834200)
    for group in item.get("expected_numbers", []):
        if not any(close_enough(n, e) for n in nums for e in group):
            return 0.0
    for word in item.get("must_include", []):
        if word.lower() not in answer.lower().replace("’", "'"):
            return 0.0
    return 1.0


def same_page(source, expected):
    return (source.get("ticker") == expected["ticker"] and source.get("fiscal_year") == expected["year"]
            and source.get("doc_file") == expected["doc_file"] and abs(source.get("page", -99) - expected["page"]) <= 1)


def citation_accuracy(item, result):
    expected = item.get("expected_sources")
    if item.get("should_refuse") or not expected:
        return None
    cited = list(result["sources"].values())
    parts = []
    if expected == "financials" or item.get("needs_financials"):
        parts.append(1.0 if any(s["type"] == "financials" for s in cited) else 0.0)
    if isinstance(expected, list):
        hit = any(s["type"] == "filing" and same_page(s, e) for s in cited for e in expected)
        parts.append(1.0 if hit else 0.0)
    return sum(parts) / len(parts)


def recall_at_5(item):
    """does plain hybrid search (no agent) put an expected page in the top 5?"""
    expected = item.get("expected_sources")
    if not isinstance(expected, list):
        return None
    results = hybrid_search(item["question"], item.get("tickers"), None, k=5)
    hit = any(same_page(r, e) for r in results for e in expected)
    return 1.0 if hit else 0.0


def tool_accuracy(item, result):
    if item.get("should_refuse"):
        return None
    return 1.0 if set(item.get("expected_tools", [])) <= set(result["tools_used"]) else 0.0


class Judgement(BaseModel):
    score: float = Field(description="1.0 = every claim supported, 0.5 = mostly supported, 0.0 = key claims unsupported")
    unsupported_claims: list[str] = Field(description="claims in the answer that the context does not support")


JUDGE_PROMPT = """You are grading an AI answer for faithfulness. Only use the CONTEXT below (tool outputs the AI saw).
Score 1.0 if every factual claim in the ANSWER is supported by the CONTEXT (numbers can be rounded or converted,
e.g. 49,696 million = 49.7 billion, and percentages computed by the calculate tool count as supported).
Score 0.5 if most claims are supported but something minor isn't. Score 0.0 if an important claim is not in the context.

QUESTION: {question}

CONTEXT:
{context}

ANSWER:
{answer}"""


def faithfulness(item, result, judge):
    """LLM as judge. judge = llm.with_structured_output(Judgement, include_raw=True)"""
    if item.get("should_refuse") or is_refusal(result["answer"]):
        return None, None, None
    context = "\n\n---\n\n".join(result.get("context", []))[:24000]
    out = judge.invoke(JUDGE_PROMPT.format(question=item["question"], context=context or "(no tool output)",
                                           answer=result["answer"]))
    usage = getattr(out["raw"], "usage_metadata", None) or {}
    if not out["parsed"]:
        return None, None, usage
    return max(0.0, min(1.0, out["parsed"].score)), out["parsed"].unsupported_claims, usage
