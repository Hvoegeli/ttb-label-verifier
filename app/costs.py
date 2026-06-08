"""Cost and usage tracking — the measured efficiency record for reviewers.

Every real extraction call appends one line to a metrics log with the actual
token usage, the actual dollar cost (computed from published per-token prices),
and the measured latency. The /stats page reads these to show totals, average
cost per label, and a transparent labor-savings comparison.

Nothing here is estimated after the fact: cost comes from the API's own usage
report multiplied by the model's real price. That is the standard a government
efficiency reviewer should be able to audit line by line.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

# Published per-million-token prices (USD), confirmed via the claude-api
# reference (cached 2026-05-26). Keep this dated and sourced.
PRICING = {
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-opus-4-8": {"input": 5.00, "output": 25.00},
}

# Where the append-only metrics log lives. Gitignored runtime data.
METRICS_PATH = Path(os.getenv("METRICS_PATH") or "metrics/usage.jsonl")


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Exact USD cost of one call from its real token usage. 0.0 for unknown models."""
    price = PRICING.get(model)
    if price is None:
        return 0.0
    return input_tokens / 1_000_000 * price["input"] + output_tokens / 1_000_000 * price["output"]


def record(model: str, input_tokens: int, output_tokens: int, cost_usd: float, latency_ms: float) -> None:
    """Append one usage record to the metrics log (best-effort; never breaks a request)."""
    rec = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost_usd, 6),
        "latency_ms": round(latency_ms, 1),
    }
    try:
        METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with METRICS_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except OSError:
        # Metrics must never take down a verification. Silently skip if unwritable.
        pass


def _read_records() -> list[dict]:
    if not METRICS_PATH.exists():
        return []
    records = []
    with METRICS_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def aggregate() -> dict:
    """Summarize the metrics log: counts, total/average cost, latency percentiles."""
    records = _read_records()
    count = len(records)
    if count == 0:
        return {
            "count": 0, "total_cost_usd": 0.0, "avg_cost_usd": 0.0,
            "total_input_tokens": 0, "total_output_tokens": 0,
            "avg_latency_ms": 0.0, "p95_latency_ms": 0.0,
            "by_model": {}, "first": None, "last": None,
        }

    total_cost = sum(r.get("cost_usd", 0.0) for r in records)
    total_in = sum(r.get("input_tokens", 0) for r in records)
    total_out = sum(r.get("output_tokens", 0) for r in records)
    latencies = sorted(r.get("latency_ms", 0.0) for r in records)
    p95_index = max(0, min(len(latencies) - 1, int(round(0.95 * (len(latencies) - 1)))))

    by_model: dict[str, dict] = {}
    for r in records:
        m = by_model.setdefault(r.get("model", "unknown"), {"count": 0, "cost_usd": 0.0})
        m["count"] += 1
        m["cost_usd"] += r.get("cost_usd", 0.0)

    return {
        "count": count,
        "total_cost_usd": total_cost,
        "avg_cost_usd": total_cost / count,
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "avg_latency_ms": sum(latencies) / count,
        "p95_latency_ms": latencies[p95_index],
        "by_model": by_model,
        "first": records[0].get("timestamp"),
        "last": records[-1].get("timestamp"),
    }
