"""Supplement validation report with August-only detailed inspections."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.vlookup.normalization import (  # noqa: E402
    normalize_client_name,
    normalize_month_year,
    normalize_name,
    parse_name_tokens,
)
from app.services.vlookup.parsers.client_hours import (  # noqa: E402
    aggregate_hours_by_candidate,
    parse_client_hours_file,
)
from app.services.vlookup.reconciliation_matcher import ReconciliationMatcher  # noqa: E402
from scripts.validate_real_business_files import (  # noqa: E402
    CLIENT_PATH,
    OUT_PATH,
    TEMPLATE_PATH,
    classify_unmatched,
    inspect_row,
    load_template,
    profile_template,
    signals_of,
    summary_of,
    templates_for_matcher,
)


def main() -> None:
    report = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    tdf = load_template(TEMPLATE_PATH)
    tprof = profile_template(tdf)
    templates = templates_for_matcher(tprof["records"])
    parsed = parse_client_hours_file(CLIENT_PATH.read_bytes(), CLIENT_PATH.name, target_month=None)
    month = "2025-08"
    month_rows = [
        r
        for r in parsed["rows"]
        if normalize_month_year(str(r.get("month") or "")) == month
    ]
    groups = aggregate_hours_by_candidate(month_rows, all_rows_for_cumulative=parsed["rows"])
    matcher = ReconciliationMatcher()
    results = matcher.match(templates, groups, target_month=month)

    flat = [r for rows in results.values() for r in rows]
    status_counts = {k: len(v) for k, v in results.items()}

    linked = {r.get("template_candidate_id") for r in flat if r.get("template_candidate_id") is not None}
    claims = defaultdict(list)
    for r in flat:
        tid = r.get("template_candidate_id")
        if tid is not None and r.get("match_status") != "unmatched":
            claims[tid].append(r.get("messy_name_original"))

    matched = list(results.get("matched") or [])
    identical, similar = [], []
    for r in matched:
        if normalize_name(r.get("messy_name_original")) == normalize_name(r.get("template_candidate_name")):
            identical.append(r)
        else:
            similar.append(r)
    sample = similar[:15] + identical[:15]
    if len(sample) < 20:
        sample += [r for r in matched if r not in sample][: 20 - len(sample)]

    # Enrich templates once for unmatched ranking
    enriched = [
        {
            **t,
            "_norm_name": normalize_name(t["candidate_name"]),
            "_name_parts": parse_name_tokens(t["candidate_name"]),
            "_norm_client": normalize_client_name(t.get("client_name")),
            "_month": t.get("month") or "",
            "_candidate_id": str(t.get("candidate_id") or "").strip().upper(),
        }
        for t in templates
    ]

    unmatched = list(results.get("unmatched") or [])
    picks = unmatched[:15] + unmatched[len(unmatched) // 3 : len(unmatched) // 3 + 8] + unmatched[-12:]
    seen = set()
    pick_rows = []
    for r in picks:
        key = (r.get("messy_name_original"), r.get("messy_client_name"))
        if key in seen:
            continue
        seen.add(key)
        pick_rows.append(r)
        if len(pick_rows) >= 35:
            break

    unmatched_inspected = []
    for r in pick_rows:
        ranked = matcher._rank_templates(
            {
                "candidate_name": r.get("messy_name_original"),
                "client_name": r.get("messy_client_name"),
                "month": r.get("messy_month"),
            },
            enriched,
            month,
        )
        best = ranked[0] if ranked else None
        info = inspect_row(r)
        if best:
            info["master_candidate"] = best["candidate"].get("candidate_name")
            info["master_client"] = best["candidate"].get("client_name")
            info["best_client_side_candidate"] = r.get("messy_name_original")
            info["best_client_side_client"] = r.get("messy_client_name")
            info["candidate_score"] = best["signals"].get("name_score")
            info["client_score"] = best["signals"].get("client_score")
            info["final_confidence"] = best.get("confidence")
            info["best_identity_compatible"] = best.get("identity_compatible")
        info["unmatched_class"] = classify_unmatched(r, best)
        unmatched_inspected.append(info)

    # Aggregation examples within August
    multi_week = [g for g in groups if len(g.get("weekly_breakdown") or {}) >= 3]
    multi_week.sort(key=lambda g: -len(g.get("weekly_breakdown") or {}))
    agg = []
    for g in multi_week[:8]:
        weeks = g.get("weekly_breakdown") or {}
        item = {
            "candidate": g.get("candidate_name"),
            "client": g.get("client_name"),
            "month": g.get("month"),
            "weekly_rows": [{"week": w, "qty_hours": h} for w, h in sorted(weeks.items())],
            "individual_qty_values": list(weeks.values()),
            "aggregated_total_hours": g.get("total_hours"),
            "source_row_count": len(g.get("source_rows") or []),
        }
        for r in flat:
            if normalize_name(r.get("messy_name_original")) == normalize_name(g.get("candidate_name")) and r.get("messy_month") == g.get("month"):
                item["final_status"] = r.get("match_status")
                item["final_master"] = r.get("template_candidate_name")
                break
        agg.append(item)

    # Dangerous FP on August
    dangerous = []
    matched_bad = []
    conflict_or_review = []
    for r in flat:
        sig = signals_of(r)
        name = float(sig.get("name_score") or 0)
        client = float(sig.get("client_score") or 0)
        if name >= 90 and sig.get("client_available") and client <= 40:
            item = inspect_row(r)
            dangerous.append(item)
            if r.get("match_status") == "matched":
                matched_bad.append(item)
            elif r.get("match_status") in ("conflicting", "needs_review"):
                conflict_or_review.append(item)

    dups = results.get("potential_duplicate") or []
    dup_report = []
    by_master = defaultdict(list)
    for r in dups:
        by_master[r.get("template_candidate_id")].append(r)
    for tid, rows in by_master.items():
        first = rows[0]
        dup_report.append(
            {
                "master_candidate": first.get("template_candidate_name"),
                "master_candidate_id": first.get("template_candidate_id_str"),
                "master_client": signals_of(first).get("template_client"),
                "client_side_identities": [
                    {
                        "client_candidate": x.get("messy_name_original"),
                        "client_client": x.get("messy_client_name"),
                        "month": x.get("messy_month"),
                        "hours": x.get("total_hours"),
                        "explanation": summary_of(x),
                    }
                    for x in rows
                ],
                "reason": summary_of(first),
            }
        )

    august = {
        "target_month": month,
        "note": (
            "This is the API auto-default month when template month (2026-07) is absent "
            "from the client file. Comparable to prior dashboard total of 714."
        ),
        "summary": {
            "total_reconciliation_records": len(flat),
            "unique_master_candidates_linked": len(linked),
            "matched": status_counts.get("matched", 0),
            "needs_review": status_counts.get("needs_review", 0),
            "unmatched": status_counts.get("unmatched", 0),
            "conflicting": status_counts.get("conflicting", 0),
            "potential_duplicate": status_counts.get("potential_duplicate", 0),
            "status_sum_ok": sum(status_counts.values()) == len(flat),
            "masters_with_no_client_link": tprof["row_count"] - len(linked),
            "masters_with_multiple_claims": sum(1 for v in claims.values() if len(v) > 1),
        },
        "matched_sample": [inspect_row(r) for r in sample[:25]],
        "needs_review_all": [inspect_row(r) for r in (results.get("needs_review") or [])],
        "conflicting_all": [inspect_row(r) for r in (results.get("conflicting") or [])],
        "potential_duplicates_all": dup_report,
        "unmatched_sample": unmatched_inspected,
        "unmatched_class_counts": dict(Counter(x["unmatched_class"] for x in unmatched_inspected)),
        "false_positive_check": {
            "high_name_low_client_cases": len(dangerous),
            "auto_matched_despite_client_disagreement": len(matched_bad),
            "sent_to_conflict_or_review": len(conflict_or_review),
            "examples": dangerous[:30],
        },
        "hours_aggregation_examples": agg,
        "final_data_quality_table": {
            "Master candidate records": tprof["row_count"],
            "Unique master candidates": tprof["unique_candidate_ids"],
            "Raw client rows (August only)": len(month_rows),
            "Unique client candidates (August groups names)": len(
                {normalize_name(g.get("candidate_name")) for g in groups}
            ),
            "Candidate-month groups": len(groups),
            "Reconciliation records": len(flat),
            "Matched": status_counts.get("matched", 0),
            "Needs Review": status_counts.get("needs_review", 0),
            "Unmatched": status_counts.get("unmatched", 0),
            "Conflicting": status_counts.get("conflicting", 0),
            "Potential Duplicate": status_counts.get("potential_duplicate", 0),
        },
    }

    # Quality from matched sample
    obvious = suspicious = 0
    for item in august["matched_sample"]:
        ns = float(item.get("candidate_score") or 0)
        cs = float(item.get("client_score") or 0)
        if ns >= 90 and cs >= 80:
            obvious += 1
        else:
            suspicious += 1
    august["match_quality_from_matched_sample"] = {
        "sample_size": len(august["matched_sample"]),
        "obvious_correct_matches": obvious,
        "suspicious_matches": suspicious,
        "likely_false_positives_dangerous_check": len(matched_bad),
    }

    report["august_2025_api_default_run"] = august
    report["primary_recommendation"] = (
        "Use August 2025 API-default run for Accounts-comparable validation. "
        "All-months run inflates Potential Duplicate because the matcher assigns "
        "one master template PK at a time across months for the same person."
    )
    OUT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(august["final_data_quality_table"], indent=2))
    print("needs_review", len(august["needs_review_all"]))
    print("conflicting", len(august["conflicting_all"]))
    print("matched_sample", len(august["matched_sample"]))
    print("fp_matched_bad", len(matched_bad))


if __name__ == "__main__":
    main()
