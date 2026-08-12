"""
Read-only validation of NEW VLOOKUP matcher against actual business files.
Does NOT modify matcher logic, thresholds, or database.
"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.vlookup.normalization import (  # noqa: E402
    normalize_client_name,
    normalize_month_year,
    normalize_name,
)
from app.services.vlookup.parsers.client_hours import (  # noqa: E402
    aggregate_hours_by_candidate,
    parse_client_hours_file,
)
from app.services.vlookup.reconciliation_matcher import ReconciliationMatcher  # noqa: E402
from app.services.vlookup.similarity import SimilarityScorer  # noqa: E402

TEMPLATE_PATH = Path(r"C:\Users\ram.bahal\Downloads\hours-template-2026-07 (1).csv")
CLIENT_PATH = Path(r"C:\Users\ram.bahal\Downloads\June-Aug,2025 Ampcus.CSV")
OUT_PATH = ROOT / "scripts" / "validation_report_real_files.json"


def load_template(path: Path) -> pd.DataFrame:
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            df = pd.read_csv(path, encoding=enc)
            break
        except Exception:
            df = None
    if df is None:
        raise RuntimeError(f"Could not read template: {path}")
    df.columns = [str(c).lower().strip().replace(" ", "_") for c in df.columns]
    return df


def profile_template(df: pd.DataFrame) -> Dict[str, Any]:
    rows = df.to_dict(orient="records")
    valid = []
    for r in rows:
        cid = str(r.get("candidate_id", "")).strip()
        if not cid or cid.lower() == "nan":
            continue
        valid.append(
            {
                "candidate_id": cid,
                "candidate_name": str(r.get("candidate_name", "") or "").strip(),
                "client_name": str(r.get("client_name", "") or "").strip(),
                "month": str(r.get("month", "") or "").strip(),
                "hours_worked": r.get("hours_worked", r.get("hours", 0)),
            }
        )
    ids = [v["candidate_id"] for v in valid]
    names = [v["candidate_name"] for v in valid]
    pairs = [(v["candidate_name"], v["client_name"]) for v in valid]
    id_counts = Counter(ids)
    dup_ids = {k: n for k, n in id_counts.items() if n > 1}
    return {
        "row_count": len(valid),
        "unique_candidate_ids": len(set(ids)),
        "unique_candidate_names": len({normalize_name(n) for n in names if n}),
        "unique_candidate_client_combos": len(
            {(normalize_name(a), normalize_client_name(b)) for a, b in pairs}
        ),
        "duplicate_candidate_id_count": len(dup_ids),
        "duplicate_candidate_id_extra_rows": sum(n - 1 for n in dup_ids.values()),
        "months": sorted({normalize_month_year(str(v.get("month") or "")) for v in valid if v.get("month")}),
        "records": valid,
    }


def profile_client(parsed: Dict[str, Any], groups: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = parsed["rows"]
    names = [r.get("candidate_name") or "" for r in rows]
    combos = [
        (normalize_name(r.get("candidate_name")), normalize_client_name(r.get("client_name")))
        for r in rows
    ]
    return {
        "format": parsed.get("format"),
        "raw_parsed_row_count": len(rows),
        "unique_extracted_candidate_names": len({normalize_name(n) for n in names if n}),
        "unique_candidate_client_combos": len({c for c in combos if c[0]}),
        "weekly_or_monthly_transaction_rows": len(rows),
        "aggregated_candidate_month_records": len(groups),
        "months_found": parsed.get("months_found") or [],
        "warnings_count": len(parsed.get("warnings") or []),
    }


def templates_for_matcher(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for i, r in enumerate(records, start=1):
        out.append(
            {
                "id": i,
                "candidate_id": r["candidate_id"],
                "candidate_name": r["candidate_name"],
                "client_name": r["client_name"],
                "month": normalize_month_year(str(r.get("month") or "")),
                "hours": float(r.get("hours_worked") or 0),
            }
        )
    return out


def flatten_results(results: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    flat = []
    for status, rows in results.items():
        for r in rows:
            flat.append(r)
    return flat


def signals_of(row: Dict[str, Any]) -> Dict[str, Any]:
    return (row.get("match_explanation") or {}).get("signals") or {}


def summary_of(row: Dict[str, Any]) -> str:
    expl = row.get("match_explanation") or {}
    return expl.get("identity_summary") or expl.get("audit", {}).get("why") or ""


def inspect_row(row: Dict[str, Any]) -> Dict[str, Any]:
    sig = signals_of(row)
    return {
        "master_candidate": row.get("template_candidate_name"),
        "master_client": sig.get("template_client") or (row.get("template_candidate") or {}).get("client_name"),
        "master_candidate_id": row.get("template_candidate_id_str"),
        "client_candidate": row.get("messy_name_original"),
        "client_client": row.get("messy_client_name"),
        "candidate_score": sig.get("name_score"),
        "client_score": sig.get("client_score"),
        "month_score": sig.get("month_score"),
        "final_confidence": row.get("confidence_score"),
        "status": row.get("match_status"),
        "explanation": summary_of(row),
        "name_band": sig.get("name_band"),
        "client_band": sig.get("client_band"),
        "month": row.get("messy_month"),
        "total_hours": row.get("total_hours"),
        "weekly_breakdown": row.get("weekly_breakdown") or {},
    }


def classify_unmatched(row: Dict[str, Any], ranked_best: Optional[Dict[str, Any]]) -> str:
    sig = signals_of(row)
    if not (row.get("messy_name_original") or "").strip():
        return "D. insufficient data"
    if ranked_best is None:
        return "A. genuinely no match"
    name = float(ranked_best.get("signals", {}).get("name_score") or sig.get("name_score") or 0)
    client = float(ranked_best.get("signals", {}).get("client_score") or 0)
    client_avail = bool(ranked_best.get("signals", {}).get("client_available"))
    identity = bool(ranked_best.get("identity_compatible"))
    if identity and name >= 90 and client_avail and client <= 40:
        return "C. client mismatch"
    if identity and 70 <= name < 90:
        return "E. possible false negative"
    if not identity and name >= 65:
        return "B. messy name that the algorithm failed to recognize"
    if not identity:
        return "A. genuinely no match"
    return "F. other"


def main() -> None:
    assert TEMPLATE_PATH.exists(), f"Missing template: {TEMPLATE_PATH}"
    assert CLIENT_PATH.exists(), f"Missing client file: {CLIENT_PATH}"

    report: Dict[str, Any] = {
        "inputs": {
            "hours_template": str(TEMPLATE_PATH),
            "client_file": str(CLIENT_PATH),
            "template_bytes": TEMPLATE_PATH.stat().st_size,
            "client_bytes": CLIENT_PATH.stat().st_size,
        }
    }

    # ---- 1. Profile template ----
    tdf = load_template(TEMPLATE_PATH)
    tprof = profile_template(tdf)
    report["hours_template_profile"] = {
        k: v for k, v in tprof.items() if k != "records"
    }

    # ---- 1. Profile client ----
    client_bytes = CLIENT_PATH.read_bytes()
    parsed = parse_client_hours_file(client_bytes, CLIENT_PATH.name, target_month=None)
    groups_all = aggregate_hours_by_candidate(
        parsed["rows"], all_rows_for_cumulative=parsed["rows"]
    )
    report["client_file_profile"] = profile_client(parsed, groups_all)

    templates = templates_for_matcher(tprof["records"])
    matcher = ReconciliationMatcher()

    # ---- 2. Full reconciliation across all months in client file ----
    results = matcher.match(templates, groups_all, target_month=None)
    status_counts = {k: len(v) for k, v in results.items()}
    flat = flatten_results(results)
    assert sum(status_counts.values()) == len(flat)

    linked_master_ids = {
        r.get("template_candidate_id")
        for r in flat
        if r.get("template_candidate_id") is not None
    }
    claims = defaultdict(list)
    for r in flat:
        tid = r.get("template_candidate_id")
        if tid is not None and r.get("match_status") in (
            "matched",
            "needs_review",
            "potential_duplicate",
            "conflicting",
        ):
            claims[tid].append(
                {
                    "client_candidate": r.get("messy_name_original"),
                    "client_client": r.get("messy_client_name"),
                    "status": r.get("match_status"),
                    "month": r.get("messy_month"),
                }
            )

    multi_claim_masters = {tid: xs for tid, xs in claims.items() if len(xs) > 1}

    report["reconciliation_summary"] = {
        "total_reconciliation_records": len(flat),
        "unique_master_candidates_linked": len(linked_master_ids),
        "matched": status_counts.get("matched", 0),
        "needs_review": status_counts.get("needs_review", 0),
        "unmatched": status_counts.get("unmatched", 0),
        "conflicting": status_counts.get("conflicting", 0),
        "potential_duplicate": status_counts.get("potential_duplicate", 0),
        "status_sum_ok": sum(status_counts.values()) == len(flat),
        "weights": {
            "name": matcher.WEIGHT_NAME,
            "client": matcher.WEIGHT_CLIENT,
            "month": matcher.WEIGHT_MONTH,
        },
        "thresholds": {
            "auto": matcher.AUTO_MATCH_THRESHOLD,
            "review": matcher.REVIEW_THRESHOLD,
            "min_identity_name": matcher.MIN_IDENTITY_NAME_SCORE,
            "strong_name": matcher.STRONG_NAME_SCORE,
            "client_strong": matcher.CLIENT_COMPAT_STRONG,
            "client_conflict_max": matcher.CLIENT_CONFLICT_MAX,
        },
    }

    # ---- 3. Master candidate coverage ----
    report["master_candidate_analysis"] = {
        "master_candidate_records": tprof["row_count"],
        "unique_master_candidate_ids": tprof["unique_candidate_ids"],
        "masters_with_at_least_one_client_link": len(linked_master_ids),
        "masters_with_no_client_link": tprof["row_count"] - len(linked_master_ids),
        "masters_with_multiple_client_side_claims": len(multi_claim_masters),
        "master_file_duplicate_candidate_ids": tprof["duplicate_candidate_id_count"],
        "relationship": (
            "Reconciliation records are client-side candidate-month groups, not master rows. "
            "One master can link to zero/one/many client-month groups; one client-month group "
            "links to at most one master."
        ),
    }

    # ---- 4. Matched sample (20+) ----
    matched = list(results.get("matched") or [])
    # Prefer diversity: exact names and non-identical names
    identical = []
    similar = []
    for r in matched:
        messy = normalize_name(r.get("messy_name_original"))
        master = normalize_name(r.get("template_candidate_name"))
        if messy == master:
            identical.append(r)
        else:
            similar.append(r)
    sample_matched = similar[:12] + identical[:12]
    if len(sample_matched) < 20:
        remaining = [r for r in matched if r not in sample_matched]
        sample_matched.extend(remaining[: 20 - len(sample_matched)])
    report["matched_sample"] = [inspect_row(r) for r in sample_matched[:25]]

    # ---- 5. All needs review ----
    report["needs_review_all"] = [inspect_row(r) for r in (results.get("needs_review") or [])]

    # ---- 6. All conflicting ----
    report["conflicting_all"] = [inspect_row(r) for r in (results.get("conflicting") or [])]

    # ---- 7. All potential duplicates ----
    dups = results.get("potential_duplicate") or []
    # Group by master id
    dup_by_master: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for r in dups:
        dup_by_master[r.get("template_candidate_id")].append(r)
    # Also include other statuses claiming same master from multi_claim_masters
    dup_report = []
    for tid, rows in sorted(dup_by_master.items(), key=lambda x: str(x[0])):
        identities = [
            {
                "client_candidate": r.get("messy_name_original"),
                "client_client": r.get("messy_client_name"),
                "month": r.get("messy_month"),
                "hours": r.get("total_hours"),
                "status": r.get("match_status"),
                "explanation": summary_of(r),
            }
            for r in rows
        ]
        # Pull sibling claims from full claims map
        siblings = claims.get(tid) or []
        first = rows[0]
        dup_report.append(
            {
                "master_candidate": first.get("template_candidate_name"),
                "master_candidate_id": first.get("template_candidate_id_str"),
                "master_client": signals_of(first).get("template_client"),
                "client_side_identities": identities,
                "all_claims_for_master": siblings,
                "reason": summary_of(first),
            }
        )
    report["potential_duplicates_all"] = dup_report

    # ---- 8. Unmatched sample (30+) with best candidate scoring ----
    unmatched = list(results.get("unmatched") or [])
    rng = random.Random(42)
    # Build variety buckets by best name score against templates (expensive but needed)
    # Use matcher._rank_templates lightly on a subset then fill
    unmatched_inspected = []
    # Take first 15 by order, then 15 from middle/end for variety
    picks = unmatched[:15]
    if len(unmatched) > 30:
        picks += unmatched[len(unmatched) // 3 : len(unmatched) // 3 + 8]
        picks += unmatched[-10:]
    else:
        picks = unmatched[:30]
    # dedupe preserving order
    seen = set()
    pick_rows = []
    for r in picks:
        key = (r.get("messy_name_original"), r.get("messy_month"), r.get("messy_client_name"))
        if key in seen:
            continue
        seen.add(key)
        pick_rows.append(r)
    while len(pick_rows) < min(30, len(unmatched)):
        r = unmatched[len(pick_rows)]
        key = (r.get("messy_name_original"), r.get("messy_month"), r.get("messy_client_name"))
        if key not in seen:
            seen.add(key)
            pick_rows.append(r)

    for r in pick_rows[:35]:
        ranked = matcher._rank_templates(
            {
                "candidate_name": r.get("messy_name_original"),
                "client_name": r.get("messy_client_name"),
                "month": r.get("messy_month"),
            },
            # enrich templates as match() does
            [
                {
                    **t,
                    "_norm_name": normalize_name(t["candidate_name"]),
                    "_name_parts": __import__(
                        "app.services.vlookup.normalization", fromlist=["parse_name_tokens"]
                    ).parse_name_tokens(t["candidate_name"]),
                    "_norm_client": normalize_client_name(t.get("client_name")),
                    "_month": t.get("month") or "",
                    "_candidate_id": str(t.get("candidate_id") or "").strip().upper(),
                }
                for t in templates
            ],
            str(r.get("messy_month") or ""),
        )
        best = ranked[0] if ranked else None
        info = inspect_row(r)
        if best:
            info["best_client_side_candidate"] = best["candidate"].get("candidate_name")
            info["best_client_side_client"] = best["candidate"].get("client_name")
            info["best_candidate_score"] = best["signals"].get("name_score")
            info["best_client_score"] = best["signals"].get("client_score")
            info["best_final_confidence"] = best.get("confidence")
            info["best_identity_compatible"] = best.get("identity_compatible")
            # For unmatched display fields requested
            info["master_candidate"] = best["candidate"].get("candidate_name")
            info["master_client"] = best["candidate"].get("client_name")
            info["candidate_score"] = best["signals"].get("name_score")
            info["client_score"] = best["signals"].get("client_score")
            info["final_confidence"] = best.get("confidence")
        info["unmatched_class"] = classify_unmatched(r, best)
        unmatched_inspected.append(info)
    report["unmatched_sample"] = unmatched_inspected
    report["unmatched_class_counts"] = dict(
        Counter(x["unmatched_class"] for x in unmatched_inspected)
    )

    # ---- 9. False positives / dangerous name-only ----
    dangerous_auto = []
    name_high_client_bad_to_conflict_or_review = []
    name_high_client_bad_matched = []
    for r in flat:
        sig = signals_of(r)
        name = float(sig.get("name_score") or 0)
        client = float(sig.get("client_score") or 0)
        client_avail = bool(sig.get("client_available"))
        if name >= 90 and client_avail and client <= 40:
            item = inspect_row(r)
            dangerous_auto.append(item)
            if r.get("match_status") == "matched":
                name_high_client_bad_matched.append(item)
            elif r.get("match_status") in ("conflicting", "needs_review"):
                name_high_client_bad_to_conflict_or_review.append(item)
    report["false_positive_check"] = {
        "high_name_low_client_cases": len(dangerous_auto),
        "auto_matched_despite_client_disagreement": len(name_high_client_bad_matched),
        "sent_to_conflict_or_review": len(name_high_client_bad_to_conflict_or_review),
        "examples": dangerous_auto[:30],
        "desired_dangerous_auto_match_count": 0,
        "actual_dangerous_auto_match_count": len(name_high_client_bad_matched),
    }

    # ---- 10. Client normalization examples from real data ----
    real_clients = sorted(
        {
            str(r.get("client_name") or "").strip()
            for r in parsed["rows"]
            if str(r.get("client_name") or "").strip()
        }
    )
    master_clients = sorted(
        {str(r.get("client_name") or "").strip() for r in tprof["records"] if r.get("client_name")}
    )
    norm_examples = []
    for raw in real_clients:
        if "abbott" in raw.lower() or ":" in raw:
            if len(norm_examples) < 25:
                norm_examples.append(
                    {"raw": raw, "normalized": normalize_client_name(raw)}
                )
    # Also compare Abbott-like master clients if any
    abbott_masters = [c for c in master_clients if "abbott" in c.lower()]
    cross = []
    for mc in abbott_masters[:5]:
        for rc in [x for x in real_clients if "abbott" in x.lower()][:8]:
            cross.append(
                {
                    "master_client": mc,
                    "client_file_client": rc,
                    "score": SimilarityScorer.client_similarity(mc, rc),
                    "norm_master": normalize_client_name(mc),
                    "norm_client": normalize_client_name(rc),
                }
            )
    # Random different-client pairs should stay low
    if master_clients and real_clients:
        diff_pairs = []
        for mc in master_clients[:20]:
            for rc in real_clients:
                if normalize_client_name(mc) and normalize_client_name(rc):
                    if normalize_client_name(mc) != normalize_client_name(rc) and normalize_client_name(mc) not in normalize_client_name(rc) and normalize_client_name(rc) not in normalize_client_name(mc):
                        sc = SimilarityScorer.client_similarity(mc, rc)
                        if sc <= 40:
                            diff_pairs.append({"master": mc, "client": rc, "score": sc})
                            break
            if len(diff_pairs) >= 8:
                break
    else:
        diff_pairs = []
    report["client_normalization"] = {
        "examples_from_client_file": norm_examples,
        "abbott_cross_scores": cross,
        "different_client_low_scores_examples": diff_pairs,
    }

    # ---- 11. Hours aggregation examples ----
    # Find groups with multiple weekly rows
    multi_week = [g for g in groups_all if len(g.get("weekly_breakdown") or {}) >= 3]
    multi_week.sort(key=lambda g: -len(g.get("weekly_breakdown") or {}))
    agg_examples = []
    for g in multi_week[:8]:
        weeks = g.get("weekly_breakdown") or {}
        agg_examples.append(
            {
                "candidate": g.get("candidate_name"),
                "client": g.get("client_name"),
                "month": g.get("month"),
                "weekly_rows": [
                    {"week": w, "qty_hours": h} for w, h in sorted(weeks.items())
                ],
                "individual_qty_values": list(weeks.values()),
                "aggregated_total_hours": g.get("total_hours"),
                "source_row_count": len(g.get("source_rows") or []),
            }
        )
    # Attach final reconciliation status for these
    for ex in agg_examples:
        key = (normalize_name(ex["candidate"]), ex["month"])
        for r in flat:
            if normalize_name(r.get("messy_name_original")) == key[0] and r.get("messy_month") == key[1]:
                ex["final_status"] = r.get("match_status")
                ex["final_master"] = r.get("template_candidate_name")
                ex["final_confidence"] = r.get("confidence_score")
                break
    report["hours_aggregation_examples"] = agg_examples

    # ---- 12. Matching unit pipeline counts ----
    # Also compute August-only (auto target) for reference
    months = sorted(
        {
            normalize_month_year(str(r.get("month") or ""))
            for r in parsed["rows"]
            if r.get("month")
        }
    )
    auto_month = months[-1] if months else None
    august_rows = [
        r
        for r in parsed["rows"]
        if normalize_month_year(str(r.get("month") or "")) == auto_month
    ]
    august_groups = aggregate_hours_by_candidate(
        august_rows, all_rows_for_cumulative=parsed["rows"]
    )
    august_results = matcher.match(templates, august_groups, target_month=auto_month)
    august_counts = {k: len(v) for k, v in august_results.items()}

    report["matching_unit_pipeline"] = {
        "raw_client_rows_parsed": len(parsed["rows"]),
        "aggregated_candidate_month_records_all_months": len(groups_all),
        "reconciliation_records_all_months": len(flat),
        "auto_target_month_if_api_default": auto_month,
        "raw_client_rows_auto_month": len(august_rows),
        "aggregated_candidate_month_records_auto_month": len(august_groups),
        "reconciliation_status_counts_auto_month": august_counts,
        "stages": [
            f"Raw client rows: {len(parsed['rows'])}",
            f"Aggregated candidate-month records (all months): {len(groups_all)}",
            f"Matched against {len(templates)} master template rows",
            f"Reconciliation records produced: {len(flat)}",
        ],
    }

    # ---- 13. Final table ----
    report["final_data_quality_table"] = {
        "Master candidate records": tprof["row_count"],
        "Unique master candidates": tprof["unique_candidate_ids"],
        "Raw client rows": len(parsed["rows"]),
        "Unique client candidates": report["client_file_profile"][
            "unique_extracted_candidate_names"
        ],
        "Candidate-month groups": len(groups_all),
        "Reconciliation records": len(flat),
        "Matched": status_counts.get("matched", 0),
        "Needs Review": status_counts.get("needs_review", 0),
        "Unmatched": status_counts.get("unmatched", 0),
        "Conflicting": status_counts.get("conflicting", 0),
        "Potential Duplicate": status_counts.get("potential_duplicate", 0),
    }

    # Match quality estimate from inspected matched sample
    obvious = 0
    suspicious = 0
    for item in report["matched_sample"]:
        cs = float(item.get("client_score") or 0)
        ns = float(item.get("candidate_score") or 0)
        if ns >= 95 and cs >= 80:
            obvious += 1
        elif ns >= 90 and cs >= 80:
            obvious += 1
        else:
            suspicious += 1
    report["match_quality_from_matched_sample"] = {
        "sample_size": len(report["matched_sample"]),
        "obvious_correct_matches": obvious,
        "suspicious_matches": suspicious,
        "likely_false_positives_in_dangerous_check": len(name_high_client_bad_matched),
        "note": "Estimates from inspected samples only; not extrapolated to full population.",
    }

    OUT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"wrote": str(OUT_PATH), "summary": report["final_data_quality_table"]}, indent=2))


if __name__ == "__main__":
    main()
