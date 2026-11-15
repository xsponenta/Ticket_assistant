"""List OpenRouter models that support structured output, with prices, and print candidate shortlists.

This script does NOT choose models: it prints rule-based candidates; the choice goes into config.yaml by hand.
Moving aliases ("~provider/...-latest") are excluded: evals need a model that does not change underneath them.

Usage:
    python scripts/list_models.py                    # cheap + mid + strong shortlists
    python scripts/list_models.py --tier mid         # one tier only
    python scripts/list_models.py --all              # + full table of eligible models
    python scripts/list_models.py --min-context 64000 --json
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from typing import Any

import requests

MODELS_URL = "https://openrouter.ai/api/v1/models"
CHEAP_N, CHEAP_MAX_PER_PROVIDER = 5, 2
STRONG_N, STRONG_MIN_OUTPUT_PRICE, STRONG_MAX_AGE_DAYS = 3, 5.0, 365
MID_N, MID_PRICE_RANGE, MID_MAX_AGE_DAYS, MID_MAX_PER_PROVIDER, MID_MIN_PROVIDERS = 10, (0.2, 3.0), 365, 2, 4
EXCLUDE_WORDS = ("preview", "deep-research")
MID_EXCLUDE_WORDS = ("preview", "deep-research", ":batch", "image", "audio", "multi-agent")  # unstable or not chat


def fetch_models() -> list[dict[str, Any]]:
    resp = requests.get(MODELS_URL, timeout=30)
    resp.raise_for_status()
    return resp.json()["data"]


def reasoning_mode(model: dict[str, Any]) -> str:
    """'mandatory', 'default-on' or 'off', from the /models `reasoning` object."""
    info = model.get("reasoning") or {}
    if info.get("mandatory"):
        return "mandatory"
    return "default-on" if info.get("default_enabled") else "off"


def per_million(price: str | None) -> float | None:
    try:
        value = float(price) * 1_000_000
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None  # -1 = variable price (routers)


def eligible_models(data: list[dict[str, Any]], min_context: int) -> list[dict[str, Any]]:
    rows = []
    for m in data:
        params = set(m.get("supported_parameters") or [])
        arch = m.get("architecture") or {}
        pin, pout = per_million(m["pricing"].get("prompt")), per_million(m["pricing"].get("completion"))
        if not ({"structured_outputs", "response_format"} & params) or pin is None or pout is None:
            continue
        if "text" not in (arch.get("output_modalities") or ["text"]) or m["id"].startswith(("openrouter/", "~")):
            continue  # "~provider/...-latest" ids are moving aliases: not reproducible, so not candidates
        if (m.get("context_length") or 0) < min_context:
            continue
        rows.append(
            {
                "id": m["id"],
                "provider": m["id"].split("/")[0],
                "context": m.get("context_length") or 0,
                "in_per_1m": round(pin, 3),
                "out_per_1m": round(pout, 3),
                "json_schema": "structured_outputs" in params,
                "created": datetime.fromtimestamp(m.get("created") or 0, UTC).date().isoformat(),
                "created_ts": m.get("created") or 0,
                "free": m["id"].endswith(":free") or (pin == 0 and pout == 0),
                "reasoning": reasoning_mode(m),
            }
        )
    return rows


def cheap_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Paid, json_schema, cheapest blended price (3 input : 1 output), at most 2 per provider."""
    pool = sorted(
        (r for r in rows if r["json_schema"] and not r["free"]),
        key=lambda r: ((3 * r["in_per_1m"] + r["out_per_1m"]) / 4, r["id"]),
    )
    picked, per_provider = [], {}
    for r in pool:
        if per_provider.get(r["provider"], 0) < CHEAP_MAX_PER_PROVIDER:
            picked.append(r)
            per_provider[r["provider"]] = per_provider.get(r["provider"], 0) + 1
        if len(picked) == CHEAP_N:
            break
    return picked


def strong_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """No quality data in the API, so price is the proxy: per provider the newest json_schema model released in the
    last 12 months with output price >= $5/1M (no preview / deep-research / free); one per provider, highest output
    price first. Returns all such per-provider picks; the first STRONG_N are the shortlist."""
    cutoff = time.time() - STRONG_MAX_AGE_DAYS * 86400
    newest: dict[str, dict[str, Any]] = {}
    for r in rows:
        if (
            not r["json_schema"]
            or r["free"]
            or r["out_per_1m"] < STRONG_MIN_OUTPUT_PRICE
            or r["created_ts"] < cutoff
            or any(w in r["id"] for w in EXCLUDE_WORDS)
        ):
            continue
        if r["provider"] not in newest or r["created_ts"] > newest[r["provider"]]["created_ts"]:
            newest[r["provider"]] = r
    return sorted(newest.values(), key=lambda r: (-r["out_per_1m"], r["id"]))


def mid_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """json_schema, output price $0.2–3 per 1M, released in the last 12 months, no free / preview / batch / image /
    audio / multi-agent; at most 2 per provider; ranked by output price (descending: price as strength proxy)."""
    cutoff = time.time() - MID_MAX_AGE_DAYS * 86400
    low, high = MID_PRICE_RANGE
    pool = sorted(
        (
            r
            for r in rows
            if r["json_schema"]
            and not r["free"]
            and low <= r["out_per_1m"] <= high
            and r["created_ts"] >= cutoff
            and not any(w in r["id"] for w in MID_EXCLUDE_WORDS)
        ),
        key=lambda r: (-r["out_per_1m"], r["id"]),
    )
    picked, per_provider = [], {}
    for r in pool:
        if per_provider.get(r["provider"], 0) < MID_MAX_PER_PROVIDER:
            picked.append(r)
            per_provider[r["provider"]] = per_provider.get(r["provider"], 0) + 1
        if len(picked) == MID_N:
            break
    return picked


def print_table(title: str, rows: list[dict[str, Any]]) -> None:
    print(f"\n{title}")
    print(
        f"  {'#':>2} {'id':<46} {'context':>9} {'$/1M in':>8} {'$/1M out':>8} {'json_schema':>11} "
        f"{'reasoning':>10} {'released':>11}"
    )
    for i, r in enumerate(rows, 1):
        print(
            f"  {i:>2} {r['id']:<46} {r['context']:>9,} {r['in_per_1m']:>8.3f} {r['out_per_1m']:>8.3f} "
            f"{'yes' if r['json_schema'] else 'no':>11} {r['reasoning']:>10} {r['created']:>11}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true", help="also print every eligible model")
    parser.add_argument("--min-context", type=int, default=32_000, help="minimum context length (default 32k)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of tables")
    parser.add_argument("--tier", choices=["all", "cheap", "mid", "strong"], default="all", help="which shortlist(s)")
    args = parser.parse_args()

    data = fetch_models()
    rows = eligible_models(data, args.min_context)
    show = {"cheap", "mid", "strong"} if args.tier == "all" else {args.tier}
    cheap, mid, strong_all = cheap_candidates(rows), mid_candidates(rows), strong_candidates(rows)
    strong, more_strong = strong_all[:STRONG_N], strong_all[STRONG_N:]
    tiers = {"cheap": cheap, "mid": mid, "strong": strong, "other_strong": more_strong}

    if args.json:
        out = {k: v for k, v in tiers.items() if k.removeprefix("other_") in show}
        print(json.dumps({**out, **({"all": rows} if args.all else {})}, indent=1))
        return

    print(
        f"OpenRouter: {len(data)} models; {len(rows)} with structured output / response_format, "
        f"text output, context >= {args.min_context:,}, fixed price, no moving ~aliases."
    )
    if "cheap" in show:
        print_table(
            f"{CHEAP_N} cheap candidates: paid, json_schema, cheapest blended price (3 in : 1 out), "
            f"<= {CHEAP_MAX_PER_PROVIDER} per provider",
            cheap,
        )
    if "mid" in show:
        low, high = MID_PRICE_RANGE
        print_table(
            f"Mid tier (top {MID_N}): json_schema, output ${low:g}–${high:g}/1M, <= {MID_MAX_AGE_DAYS} days old, "
            f"no free/preview/batch/image/audio/multi-agent, <= {MID_MAX_PER_PROVIDER} per provider, by output price",
            mid,
        )
        n_providers = len({r["provider"] for r in mid})
        status = "ok" if n_providers >= MID_MIN_PROVIDERS else f"FEWER THAN {MID_MIN_PROVIDERS}"
        print(f"  providers in mid tier: {n_providers} ({status})")
    if "strong" in show:
        print_table(
            f"{STRONG_N} strong candidates: price as quality proxy: per provider the newest json_schema model "
            f"(<= {STRONG_MAX_AGE_DAYS} days old, output >= ${STRONG_MIN_OUTPUT_PRICE:g}/1M), highest output price",
            strong,
        )
        if more_strong:
            print_table("Other per-provider flagships (same rule)", more_strong)
    providers = {r["provider"] for tier in show for r in tiers[tier]}
    print(f"\nProviders in the shortlists: {len(providers)} ({', '.join(sorted(providers))}).")
    print("These are candidates only. Put your choice in config.yaml (models.generator / judge / simulator).")
    if args.all:
        print_table("All eligible models (by provider, id)", sorted(rows, key=lambda r: r["id"]))


if __name__ == "__main__":
    main()
