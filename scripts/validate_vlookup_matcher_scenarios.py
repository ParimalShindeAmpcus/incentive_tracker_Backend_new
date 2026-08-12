"""Synthetic validation report for client-gated matcher."""

from __future__ import annotations

from collections import defaultdict

from app.services.vlookup.normalization import normalize_month_year, normalize_name
from app.services.vlookup.reconciliation_matcher import ReconciliationMatcher


def main() -> None:
    m = ReconciliationMatcher()
    templates = [
        {
            "id": 1,
            "candidate_id": "A1",
            "candidate_name": "John Smith",
            "client_name": "Microsoft",
            "month": "2025-08",
        },
        {
            "id": 2,
            "candidate_id": "A2",
            "candidate_name": "Ram Bahal",
            "client_name": "Abbott",
            "month": "2025-08",
        },
        {
            "id": 3,
            "candidate_id": "A3",
            "candidate_name": "Jeneria Chonice Hopkins",
            "client_name": "DOMINION ENERGY",
            "month": "2025-08",
        },
        {
            "id": 4,
            "candidate_id": "A4",
            "candidate_name": "Alice Johnson",
            "client_name": "Acme Corp",
            "month": "2025-08",
        },
        {
            "id": 5,
            "candidate_id": "A5",
            "candidate_name": "Michael Brown",
            "client_name": "Globex",
            "month": "2025-08",
        },
    ]

    raw_rows = [
        {
            "candidate_name": "John Smith",
            "client_name": "Microsoft",
            "month": "2025-08",
            "hours": 40,
            "week": "2025-08-01",
        },
        {
            "candidate_name": "Bahal, Ram",
            "client_name": "Abbott:4215",
            "month": "2025-08",
            "hours": 40,
            "week": "2025-08-01",
        },
        {
            "candidate_name": "R Bahal",
            "client_name": "Abbott",
            "month": "2025-07",
            "hours": 32,
            "week": "2025-07-01",
        },
        {
            "candidate_name": "Jeneria Chonice Hopkins",
            "client_name": "Abbott:4215",
            "month": "2025-08",
            "hours": 40,
            "week": "2025-08-01",
        },
        {
            "candidate_name": "Jeneria Chonice Hopkins",
            "client_name": "DOMINION ENERGY",
            "month": "2025-07",
            "hours": 40,
            "week": "2025-07-01",
        },
        {
            "candidate_name": "Robert Patel",
            "client_name": "Microsoft",
            "month": "2025-08",
            "hours": 40,
            "week": "2025-08-01",
        },
        {
            "candidate_name": "Alice Johnson",
            "client_name": "Acme Corp",
            "month": "2025-08",
            "hours": 40,
            "week": "2025-08-07",
        },
        {
            "candidate_name": "Alice Johnson",
            "client_name": "Acme Corp",
            "month": "2025-08",
            "hours": 40,
            "week": "2025-08-14",
        },
        {
            "candidate_name": "Alice Johnson",
            "client_name": "Acme Corp",
            "month": "2025-08",
            "hours": 32,
            "week": "2025-08-21",
        },
        {
            "candidate_name": "Michael Brown",
            "client_name": "",
            "month": "2025-08",
            "hours": 40,
            "week": "2025-08-01",
        },
        {
            "candidate_name": "",
            "client_name": "Globex",
            "month": "2025-08",
            "hours": 10,
            "week": "2025-08-01",
        },
    ]

    bucket = defaultdict(
        lambda: {"hours": 0.0, "weeks": {}, "client": "", "name": "", "rows": 0}
    )
    for r in raw_rows:
        key = (normalize_name(r["candidate_name"]), normalize_month_year(r["month"]))
        b = bucket[key]
        b["hours"] += r["hours"]
        b["weeks"][r["week"]] = b["weeks"].get(r["week"], 0) + r["hours"]
        b["client"] = r["client_name"] or b["client"]
        b["name"] = r["candidate_name"] or b["name"]
        b["rows"] += 1

    groups = []
    for (n, month), b in bucket.items():
        groups.append(
            {
                "candidate_name": b["name"] or n,
                "client_name": b["client"],
                "month": month,
                "total_hours": b["hours"],
                "weekly_breakdown": b["weeks"],
                "source_rows": [{}] * b["rows"],
            }
        )

    results = m.match(templates, groups, target_month="2025-08")
    counts = {k: len(v) for k, v in results.items()}
    print("SCENARIO_COUNTS", counts)
    print("TOTAL", sum(counts.values()))
    for status, rows in results.items():
        for row in rows:
            print(
                f"{status:20} | {row.get('messy_name_original')!r:40} | "
                f"client={row.get('messy_client_name')!r:30} | "
                f"-> {row.get('template_candidate_name')!r} | "
                f"conf={row.get('confidence_score')} | "
                f"{(row['match_explanation'].get('identity_summary') or '')[:100]}"
            )

    wrong = [
        r
        for r in results["matched"]
        if "Abbott" in str(r.get("messy_client_name"))
        and r.get("template_candidate_name") == "Jeneria Chonice Hopkins"
    ]
    print("FALSE_POSITIVE_WRONG_CLIENT_MATCHED", len(wrong))

    # Weights / thresholds snapshot
    print(
        "WEIGHTS",
        {"name": m.WEIGHT_NAME, "client": m.WEIGHT_CLIENT, "month": m.WEIGHT_MONTH},
    )
    print(
        "THRESHOLDS",
        {
            "auto": m.AUTO_MATCH_THRESHOLD,
            "review": m.REVIEW_THRESHOLD,
            "min_name": m.MIN_IDENTITY_NAME_SCORE,
            "strong_name": m.STRONG_NAME_SCORE,
            "client_strong": m.CLIENT_COMPAT_STRONG,
            "client_conflict_max": m.CLIENT_CONFLICT_MAX,
            "ambiguity_gap": m.AMBIGUITY_GAP,
        },
    )


if __name__ == "__main__":
    main()
