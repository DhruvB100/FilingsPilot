"""
Runs the golden set through the agent and scores it.

python -m evals.run                       # all 50 questions, azure  (~$0.30)
python -m evals.run --subset ci           # the 10 CI questions      (~$0.06)
python -m evals.run --ids A01,C03         # just some
python -m evals.run --provider gemini     # model comparison, costs GCP money, run once by hand
python -m evals.run --subset ci --check evals/baseline_ci.json   # exit 1 if scores dropped (used in CI)
"""
import os
import sys
import csv
import json
import argparse
import subprocess
import statistics

os.environ["JIRA_DRY_RUN"] = "1"  # never create real jira tickets from evals

from backend import llm as llm_module  # noqa: E402
from backend.agent import run_agent  # noqa: E402
from evals import scorers  # noqa: E402

HERE = os.path.dirname(__file__)
METRICS = ["answer_correctness", "faithfulness", "citation_accuracy", "recall_at_5", "tool_accuracy"]


def git_info():
    # results are tied to the commit they were run on
    try:
        sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
        date = subprocess.check_output(["git", "log", "-1", "--format=%cI"], text=True).strip()
        return sha, date
    except Exception:
        return "unknown", ""


def avg(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 3) if values else None


def p95(values):
    values = sorted(values)
    if not values:
        return None
    return round(values[min(len(values) - 1, int(round(0.95 * (len(values) - 1))))], 2)


def run(args):
    with open(os.path.join(HERE, "golden_set.json")) as f:
        items = json.load(f)
    if args.subset == "ci":
        items = [i for i in items if i.get("ci")]
    if args.ids:
        wanted = args.ids.split(",")
        items = [i for i in items if i["id"] in wanted]
    if args.limit:
        items = items[: args.limit]

    # judge is always the azure model so both providers get graded the same way
    judge = llm_module.get_llm("azure", max_tokens=1500).with_structured_output(scorers.Judgement, include_raw=True)

    rows = []
    total_cost = 0.0
    judge_cost = 0.0
    for n, item in enumerate(items, 1):
        if total_cost + judge_cost > args.max_cost:
            print(f"!! stopping, hit max cost ${args.max_cost}")
            break
        try:
            result = run_agent(item["question"], provider=args.provider)
        except Exception as e:
            print(f"{item['id']} ERROR {e!r}")
            rows.append({"id": item["id"], "category": item["category"], "error": repr(e)[:300]})
            continue
        total_cost += result["cost_usd"]

        row = {
            "id": item["id"], "category": item["category"], "question": item["question"],
            "answer": result["answer"], "tools_used": result["tools_used"],
            "cited": {k: {kk: v.get(kk) for kk in ("type", "ticker", "fiscal_year", "doc_file", "page", "sql")}
                      for k, v in result["sources"].items()},
            "answer_correctness": scorers.answer_correctness(item, result),
            "citation_accuracy": scorers.citation_accuracy(item, result),
            "recall_at_5": scorers.recall_at_5(item),
            "tool_accuracy": scorers.tool_accuracy(item, result),
            "latency_s": result["latency_s"], "cost_usd": result["cost_usd"],
            "input_tokens": result["input_tokens"], "output_tokens": result["output_tokens"],
        }
        if args.no_judge:
            row["faithfulness"] = None
        else:
            score, unsupported, usage = scorers.faithfulness(item, result, judge)
            row["faithfulness"], row["unsupported_claims"] = score, unsupported
            if usage:
                judge_cost += llm_module.cost("azure", usage.get("input_tokens", 0), usage.get("output_tokens", 0))
        rows.append(row)
        print(f"[{n}/{len(items)}] {item['id']} correct={row['answer_correctness']} faith={row['faithfulness']} "
              f"cite={row['citation_accuracy']} recall={row['recall_at_5']} tools={row['tool_accuracy']} "
              f"{row['latency_s']}s ${row['cost_usd']:.4f}")

    ok = [r for r in rows if "error" not in r]
    sha, commit_date = git_info()
    summary = {
        "commit": sha, "commit_date": commit_date, "provider": args.provider or os.getenv("LLM_PROVIDER", "azure"),
        "subset": args.subset or ("custom" if args.ids else "full"), "questions": len(rows), "errors": len(rows) - len(ok),
        **{m: avg([r[m] for r in ok]) for m in METRICS},
        "avg_latency_s": avg([r["latency_s"] for r in ok]),
        "p95_latency_s": p95([r["latency_s"] for r in ok]),
        "agent_cost_usd": round(total_cost, 4),
        "judge_cost_usd": round(judge_cost, 4),
        "cost_per_question_usd": round(total_cost / max(1, len(ok)), 5),
    }
    # per category accuracy is useful for spotting what broke
    for cat in sorted({r["category"] for r in ok}):
        summary[f"correct_{cat}"] = avg([r["answer_correctness"] for r in ok if r["category"] == cat])

    print(json.dumps(summary, indent=2))

    if not args.no_save:
        os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
        name = f"{sha}_{summary['provider']}_{summary['subset']}.json"
        with open(os.path.join(HERE, "results", name), "w") as f:
            json.dump({"summary": summary, "items": rows}, f, indent=1)
        hist = os.path.join(HERE, "results", "history.csv")
        new = not os.path.exists(hist)
        with open(hist, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(summary.keys()), extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerow(summary)
        print("saved", name)

    if args.check:
        return check(summary, args.check, args.tolerance)
    return 0


def check(summary, baseline_path, tolerance):
    with open(baseline_path) as f:
        baseline = json.load(f)
    failed = False
    for m in METRICS:
        if baseline.get(m) is None or summary.get(m) is None:
            continue
        status = "ok"
        if summary[m] < baseline[m] - tolerance:
            status = "DROPPED"
            failed = True
        print(f"{m:20s} now {summary[m]:.3f}  baseline {baseline[m]:.3f}  {status}")
    if summary["errors"]:
        print(f"{summary['errors']} questions errored")
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--subset", choices=["ci"])
    p.add_argument("--ids")
    p.add_argument("--limit", type=int)
    p.add_argument("--provider", choices=["azure", "gemini"])
    p.add_argument("--max-cost", type=float, default=1.0, help="stop if this run costs more than this (USD)")
    p.add_argument("--no-judge", action="store_true")
    p.add_argument("--no-save", action="store_true")
    p.add_argument("--check", help="baseline json, exit 1 if any metric drops more than --tolerance")
    p.add_argument("--tolerance", type=float, default=0.1)
    sys.exit(run(p.parse_args()))
