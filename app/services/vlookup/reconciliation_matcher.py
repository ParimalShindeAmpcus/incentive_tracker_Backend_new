"""
Candidate + client gated matching for Hours Template vs client hours.

Design principles:
- Candidate name is necessary but not sufficient for automatic matches
- Client identity is an independent validation signal that can block auto-match
- Alternatives only include identity-compatible, non-conflicting reference candidates
- Ambiguity is relative among plausible name variants
- Hours/business validation is separate from identity status
- No person/client-specific hardcoded cases
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

from app.config import get_settings

def _settings():
    return get_settings()

from app.services.vlookup.normalization import (
    extract_person_name,
    normalize_client_name,
    normalize_month_year,
    normalize_name,
    parse_name_tokens,
)
from app.services.vlookup.similarity import SimilarityScorer, name_feature_scores


class ReconciliationMatcher:
    """Match messy client people to Hours Template reference candidates."""

    def __init__(
        self,
        auto_threshold: float = None,
        review_threshold: float = None,
        ambiguity_gap: float = None,
        hours_validation_cap: float = None,
    ):
        settings = get_settings()

        self.AUTO_MATCH_THRESHOLD = float(
            auto_threshold if auto_threshold is not None
            else getattr(settings, "THRESHOLD_AUTO_MATCH", getattr(settings, "threshold_auto_match", 88.0))
        )
        # Settings historically used very high auto thresholds; clamp legacy 99+ defaults.
        if self.AUTO_MATCH_THRESHOLD >= 99:
            self.AUTO_MATCH_THRESHOLD = 88.0

        self.REVIEW_THRESHOLD = float(
            review_threshold if review_threshold is not None
            else getattr(settings, "THRESHOLD_REVIEW", getattr(settings, "threshold_review", 70.0))
        )
        if self.REVIEW_THRESHOLD >= 95:
            self.REVIEW_THRESHOLD = 70.0

        self.AMBIGUITY_GAP = float(
            ambiguity_gap
            if ambiguity_gap is not None
            else getattr(settings, "vlookup_ambiguity_gap", 8.0)
        )
        self.HOURS_VALIDATION_CAP = float(
            hours_validation_cap
            if hours_validation_cap is not None
            else getattr(settings, "HOURS_VALIDATION_CAP", getattr(settings, "hours_validation_cap", 160.0))
        )

        # Configurable signal weights (renormalized per pair when signals absent)
        self.WEIGHT_NAME = float(getattr(settings, "vlookup_weight_name", 0.60))
        self.WEIGHT_CLIENT = float(getattr(settings, "vlookup_weight_client", 0.30))
        self.WEIGHT_MONTH = float(getattr(settings, "vlookup_weight_month", 0.10))

        # Identity / client decision bands
        self.MIN_IDENTITY_NAME_SCORE = float(
            getattr(settings, "vlookup_min_identity_name_score", 70.0)
        )
        self.STRONG_NAME_SCORE = float(getattr(settings, "vlookup_strong_name_score", 90.0))
        self.MODERATE_NAME_SCORE = float(getattr(settings, "vlookup_moderate_name_score", 78.0))
        self.CLIENT_COMPAT_STRONG = float(getattr(settings, "vlookup_client_compat_strong", 80.0))
        self.CLIENT_COMPAT_MODERATE = float(
            getattr(settings, "vlookup_client_compat_moderate", 55.0)
        )
        self.CLIENT_CONFLICT_MAX = float(getattr(settings, "vlookup_client_conflict_max", 40.0))

        self.ALT_RELATIVE_FLOOR = 0.82  # alternative must be >= 82% of top name score
        self.ALT_MIN_CLIENT_WHEN_TOP_HAS_CLIENT = 45.0
        self.LAST_NAME_FUZZY_MIN = 88.0
        self.FIRST_NAME_FUZZY_MIN = 85.0

        self.scorer = SimilarityScorer()

    def match(
        self,
        template_candidates: List[Dict[str, Any]],
        client_groups: List[Dict[str, Any]],
        target_month: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Hours Template is the master list.

        Each template candidate is matched once against client-file identities.
        Extra people in the messy file who are not on the Hours Template are
        ignored (they are not our candidates and must not appear as unmatched).
        """
        target = normalize_month_year(target_month) if target_month else ""
        identity_groups = self._collapse_client_identities(client_groups)

        templates = []
        for t in template_candidates:
            parsed = parse_name_tokens(t.get("candidate_name"))
            templates.append({
                **t,
                "_norm_name": parsed["normalized"],
                "_name_parts": parsed,
                "_norm_client": normalize_client_name(t.get("client_name")),
                "_month": normalize_month_year(str(t.get("month") or target or "")),
                "_candidate_id": str(t.get("candidate_id") or "").strip().upper(),
            })
        name_counts: Dict[str, int] = defaultdict(int)
        name_client_counts: Dict[Tuple[str, str], int] = defaultdict(int)
        for t in templates:
            name_counts[t["_norm_name"]] += 1
            name_client_counts[(t["_norm_name"], t["_norm_client"])] += 1
        for t in templates:
            t["_homonym_count"] = name_counts[t["_norm_name"]]
            t["_homonym_same_client"] = name_client_counts[(t["_norm_name"], t["_norm_client"])]

        by_norm: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        by_last: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        by_compact: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        name_to_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for g in identity_groups:
            extracted = extract_person_name(g.get("candidate_name")) or g.get("candidate_name")
            parsed = parse_name_tokens(extracted)
            g["_norm_name"] = parsed["normalized"]
            g["_name_parts"] = parsed
            g["_norm_client"] = normalize_client_name(g.get("client_name"))
            g["_messy_key"] = (g["_norm_name"], g["_norm_client"])
            if g["_norm_name"]:
                by_norm[g["_norm_name"]].append(g)
                name_to_groups[g["_norm_name"]].append(g)
            last = parsed.get("last") or ""
            if last:
                by_last[last].append(g)
            compact = str(parsed.get("compact") or "")
            if compact:
                by_compact[compact].append(g)
        name_choices = list(name_to_groups.keys())

        scored_pairs = []
        for template in templates:
            ranked = self._rank_groups_for_template(
                template,
                identity_groups,
                target,
                by_norm=by_norm,
                by_last=by_last,
                by_compact=by_compact,
                name_choices=name_choices,
                name_to_groups=name_to_groups,
            )
            scored_pairs.append({"template": template, "candidates": ranked})

        scored_pairs.sort(
            key=lambda p: (
                p["candidates"][0]["identity_compatible"],
                p["candidates"][0]["confidence"],
            ) if p["candidates"] else (False, -1),
            reverse=True,
        )

        assigned_messy_keys = set()
        pending = []
        for pair in scored_pairs:
            record = self._build_template_match_record(
                pair["template"], pair["candidates"], assigned_messy_keys, target
            )
            pending.append(record)
            messy_key = record.get("_messy_key")
            if messy_key and record["match_status"] != "unmatched":
                assigned_messy_keys.add(messy_key)

        results = {
            "matched": [],
            "needs_review": [],
            "unmatched": [],
            "potential_duplicate": [],
            "conflicting": [],
            "accepted": [],
            "rejected": [],
        }

        for record in pending:
            record.pop("_messy_key", None)
            explanation = record.setdefault("match_explanation", {})
            hours = float(record.get("total_hours") or 0)
            cumulative = float(record.get("cumulative_hours") or hours)

            explanation["cumulative_hours"] = cumulative
            explanation["monthly_hours"] = record.get("monthly_hours") or {}
            explanation["weekly_by_month"] = record.get("weekly_by_month") or {}
            explanation["hours_note"] = record.get("hours_note") or ""
            if hours > 0 or explanation["monthly_hours"]:
                explanation["hours_source"] = (
                    "Hours Worked filled from client weekly rows (template started at 0)"
                )

            validation = self._hours_validation(hours)
            record["validation_status"] = validation["status"]
            explanation["validation"] = validation

            signals = explanation.get("signals") or {}
            flags = explanation.get("identity_flags") or []
            if (
                record.get("messy_name_original")
                and signals.get("identity_compatible")
                and signals.get("client_available")
                and float(signals.get("name_score") or 0) >= self.STRONG_NAME_SCORE
                and float(signals.get("client_score") or 0) <= self.CLIENT_CONFLICT_MAX
                and record["match_status"] in ("matched", "needs_review")
                and "identity_already_assigned" not in flags
            ):
                explanation.setdefault("identity_flags", []).append(
                    "client_mismatch_with_strong_name"
                )
                record["match_status"] = "conflicting"
                explanation["identity_summary"] = (
                    "Candidate identity is strong, but client identity conflicts with the "
                    "master client."
                )
                explanation["identity_headline"] = (
                    f"Conflict: {record.get('template_candidate_name')}"
                )
                explanation["audit"] = self._audit_block(
                    headline=explanation["identity_headline"],
                    why=explanation["identity_summary"],
                    identity_status="conflicting",
                    validation=validation,
                    master_candidate=record.get("template_candidate_name"),
                    master_client=signals.get("template_client"),
                    client_candidate=record.get("messy_name_original"),
                    client_client=record.get("messy_client_name"),
                    candidate_similarity=float(signals.get("name_score") or 0),
                    client_similarity=float(signals.get("client_score") or 0),
                    final_confidence=float(record.get("confidence_score") or 0),
                )

            if "audit" not in explanation:
                explanation["audit"] = self._audit_block(
                    headline=explanation.get("identity_headline") or record.get("match_status"),
                    why=explanation.get("identity_summary") or "",
                    identity_status=record.get("match_status"),
                    validation=validation,
                    alternatives=explanation.get("alternatives") or [],
                    master_candidate=record.get("template_candidate_name"),
                    master_client=signals.get("template_client"),
                    client_candidate=record.get("messy_name_original"),
                    client_client=record.get("messy_client_name"),
                    candidate_similarity=float(signals.get("name_score") or 0)
                    if signals
                    else None,
                    client_similarity=float(signals.get("client_score") or 0)
                    if signals.get("client_available")
                    else None,
                    final_confidence=float(record.get("confidence_score") or 0),
                )

            results.setdefault(record["match_status"], []).append(record)

        return results

    def _collapse_client_identities(self, groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge month-split client groups into one identity (name + client)."""
        merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for group in groups:
            name = group.get("candidate_name") or ""
            client = group.get("client_name") or ""
            key = (normalize_name(name), normalize_client_name(client))
            if key not in merged:
                monthly = dict(group.get("monthly_hours") or {})
                if group.get("month") and group.get("total_hours") and group["month"] not in monthly:
                    monthly[str(group["month"])] = float(group.get("total_hours") or 0)
                weekly_by_month = dict(group.get("weekly_by_month") or {})
                if group.get("month") and group.get("weekly_breakdown") and group["month"] not in weekly_by_month:
                    weekly_by_month[str(group["month"])] = dict(group.get("weekly_breakdown") or {})
                prefixes = set(group.get("invoice_prefixes") or [])
                merged[key] = {
                    **group,
                    "monthly_hours": monthly,
                    "weekly_by_month": weekly_by_month,
                    "invoice_prefixes": sorted(prefixes),
                    "total_hours": float(group.get("total_hours") or 0),
                    "cumulative_hours": float(
                        group.get("cumulative_hours") or group.get("total_hours") or 0
                    ),
                }
                continue

            dest = merged[key]
            dest["total_hours"] = float(dest.get("total_hours") or 0) + float(group.get("total_hours") or 0)
            dest["cumulative_hours"] = max(
                float(dest.get("cumulative_hours") or 0),
                float(group.get("cumulative_hours") or 0),
                dest["total_hours"],
            )
            for month, hours in (group.get("monthly_hours") or {}).items():
                dest["monthly_hours"][month] = float(dest["monthly_hours"].get(month, 0)) + float(hours)
            month = str(group.get("month") or "")
            if month and month not in dest["monthly_hours"] and group.get("total_hours"):
                dest["monthly_hours"][month] = float(
                    dest["monthly_hours"].get(month, 0)
                ) + float(group.get("total_hours") or 0)
            for month, weeks in (group.get("weekly_by_month") or {}).items():
                dest["weekly_by_month"].setdefault(month, {})
                for week, hours in (weeks or {}).items():
                    dest["weekly_by_month"][month][week] = float(
                        dest["weekly_by_month"][month].get(week, 0)
                    ) + float(hours)
            if month and group.get("weekly_breakdown") and month not in (group.get("weekly_by_month") or {}):
                dest["weekly_by_month"].setdefault(month, {})
                for week, hours in (group.get("weekly_breakdown") or {}).items():
                    dest["weekly_by_month"][month][week] = float(
                        dest["weekly_by_month"][month].get(week, 0)
                    ) + float(hours)
            dest_prefixes = set(dest.get("invoice_prefixes") or [])
            dest_prefixes.update(group.get("invoice_prefixes") or [])
            dest["invoice_prefixes"] = sorted(dest_prefixes)
            if len(str(name)) > len(str(dest.get("candidate_name") or "")):
                dest["candidate_name"] = name
            dest["source_rows"] = (dest.get("source_rows") or []) + (group.get("source_rows") or [])
        return list(merged.values())

    def _rank_groups_for_template(
        self,
        template: Dict[str, Any],
        groups: List[Dict[str, Any]],
        target_month: str,
        *,
        by_norm: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        by_last: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        by_compact: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        name_choices: Optional[List[str]] = None,
        name_to_groups: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> List[Dict[str, Any]]:
        """Rank messy-file identities for one Hours Template candidate."""
        t_norm = template.get("_norm_name") or ""
        t_parts = template.get("_name_parts") or parse_name_tokens(template.get("candidate_name"))
        pool: Dict[Any, Dict[str, Any]] = {}

        def _add(rows: List[Dict[str, Any]]) -> None:
            for g in rows:
                key = g.get("_messy_key") or id(g)
                pool[key] = g

        if by_norm and t_norm:
            _add(by_norm.get(t_norm, []))

        last = t_parts.get("last") or ""
        if by_last and last:
            _add(by_last.get(last, []))

        compact = str(t_parts.get("compact") or "")
        if by_compact and compact:
            _add(by_compact.get(compact, []))

        if name_choices is not None and name_to_groups is not None and len(pool) < 25 and t_norm:
            from rapidfuzz import process

            hits = process.extract(
                t_norm,
                name_choices,
                scorer=fuzz.token_set_ratio,
                limit=40,
                score_cutoff=65,
            )
            for choice, _score, _idx in hits:
                _add(name_to_groups.get(choice, []))

        candidates = list(pool.values()) if pool else groups
        if len(candidates) > 80 and name_choices is not None and name_to_groups is not None:
            from rapidfuzz import process

            hits = process.extract(
                t_norm,
                name_choices,
                scorer=fuzz.WRatio,
                limit=80,
                score_cutoff=55,
            )
            trimmed: Dict[Any, Dict[str, Any]] = {}
            for choice, _score, _idx in hits:
                for g in name_to_groups.get(choice, []):
                    trimmed[g.get("_messy_key", id(g))] = g
            if trimmed:
                candidates = list(trimmed.values())

        ranked = []
        for group in candidates:
            scored = self._score_pair(group, template, target_month, messy_parts=group.get("_name_parts"))
            scored["group"] = group
            scored["messy_key"] = group.get("_messy_key") or (
                normalize_name(group.get("candidate_name")),
                normalize_client_name(group.get("client_name")),
            )
            ranked.append(scored)
        ranked.sort(
            key=lambda x: (x["identity_compatible"], x["confidence"], x["signals"]["name_score"]),
            reverse=True,
        )
        return ranked

    def _build_template_match_record(
        self,
        template: Dict[str, Any],
        ranked: List[Dict[str, Any]],
        assigned_messy_keys: set,
        target_month: str,
    ) -> Dict[str, Any]:
        available = [
            r for r in ranked
            if r.get("messy_key") not in assigned_messy_keys
        ]
        compatible = [r for r in available if r.get("identity_compatible")]
        claimed_compatible = [
            r for r in ranked
            if r.get("identity_compatible") and r.get("messy_key") in assigned_messy_keys
        ]
        identity_already_assigned = False
        best = compatible[0] if compatible else (available[0] if available else None)
        second = compatible[1] if len(compatible) > 1 else None
        # Same person exists in the client file, but another Hours Template row
        # already claimed that identity. Do not hide it as "not in client file".
        if not compatible and claimed_compatible:
            best = claimed_compatible[0]
            second = None
            identity_already_assigned = True

        group = (best or {}).get("group") or {}
        monthly_hours = dict(group.get("monthly_hours") or {})
        weekly_by_month = dict(group.get("weekly_by_month") or {})
        if target_month and monthly_hours.get(target_month) is not None:
            hours_out = int(round(float(monthly_hours.get(target_month) or 0)))
            weekly = dict((weekly_by_month.get(target_month) or group.get("weekly_breakdown") or {}))
        else:
            hours_out = int(round(float(group.get("total_hours") or 0)))
            weekly = dict(group.get("weekly_breakdown") or {})
        cumulative_hours = float(group.get("cumulative_hours") or hours_out)
        hours_note = group.get("hours_note") or ""
        validation = self._hours_validation(hours_out)

        base_fields = {
            "template_candidate": template,
            "template_candidate_id": template.get("id"),
            "template_candidate_name": template.get("candidate_name"),
            "template_candidate_id_str": template.get("candidate_id"),
            "messy_name_original": group.get("candidate_name") if best else None,
            "messy_client_name": group.get("client_name") if best else None,
            "messy_month": (group.get("month") or target_month) if best else (target_month or template.get("_month")),
            "weekly_records": group.get("source_rows") or [],
            "weekly_breakdown": weekly,
            "total_hours": hours_out,
            "cumulative_hours": cumulative_hours,
            "monthly_hours": monthly_hours,
            "weekly_by_month": weekly_by_month,
            "hours_note": hours_note,
            "validation_status": validation["status"],
        }

        if not best:
            summary = (
                "This Hours Template candidate was not found in the client hours file."
            )
            explanation = {
                "identity_summary": summary,
                "identity_headline": "Unmatched",
                "signals": {},
                "alternatives": [],
                "identity_flags": ["not_in_client_file"],
                "validation": validation,
                "audit": self._audit_block(
                    headline="Unmatched",
                    why=summary,
                    identity_status="unmatched",
                    validation=validation,
                    master_candidate=template.get("candidate_name"),
                    master_client=template.get("client_name"),
                    final_confidence=0.0,
                ),
            }
            return {
                **base_fields,
                "messy_name_original": None,
                "messy_client_name": None,
                "confidence_score": 0.0,
                "match_method": "none",
                "match_status": "unmatched",
                "match_explanation": explanation,
                "alternatives": [],
                "_messy_key": None,
            }

        decision = self._decide_status(group, best, None)
        status = decision["status"]
        summary = decision["summary"]
        headline = decision["headline"]
        flags = list(decision["flags"])

        if (
            status in ("matched", "needs_review")
            and second
            and second.get("identity_compatible")
            and (best["confidence"] - second["confidence"]) < self.AMBIGUITY_GAP
            and float(second["signals"].get("name_score") or 0) >= self.MIN_IDENTITY_NAME_SCORE
        ):
            other = (second.get("group") or {}).get("candidate_name")
            status = "potential_duplicate"
            summary = (
                f"Two client-file identities appear to claim "
                f"'{template.get('candidate_name')}': '{group.get('candidate_name')}' "
                f"and '{other}'. Confirm which hours belong to this Hours Template candidate."
            )
            headline = f"Potential duplicate: {template.get('candidate_name')}"
            flags.append("ambiguous_client_identities")

        if (
            status == "matched"
            and int(template.get("_homonym_same_client") or 1) > 1
        ):
            status = "needs_review"
            flags.append("master_name_not_unique")
            summary = (
                f"Normalized name is shared by {template.get('_homonym_same_client')} "
                "Hours Template candidates at the same client. Confirm which person is correct."
            )
            headline = f"Needs review: {template.get('candidate_name')}"

        if identity_already_assigned:
            claimed_group = (best.get("group") or {}) if best else {}
            claimed_client = claimed_group.get("client_name") or "the client file"
            flags.append("identity_already_assigned")
            if int(template.get("_homonym_count") or 1) > 1:
                flags.append("master_name_not_unique")
            status = "needs_review"
            summary = (
                f"This name exists in the client hours file, but those hours are already "
                f"linked to another Hours Template row so they are not counted twice. "
                f"Client-file identity '{claimed_group.get('candidate_name')}' / "
                f"'{claimed_client}'. Confirm which Candidate ID is correct."
            )
            headline = f"Needs review: {template.get('candidate_name')}"

        if status == "unmatched":
            summary = (
                "This Hours Template candidate was not found in the client hours file "
                "with a sufficiently reliable identity match."
            )
            headline = "Unmatched"
            linked_group = None
            messy_key = None
            alts = self._plausible_alternatives_from_groups(compatible, best)
        elif identity_already_assigned:
            linked_group = group
            messy_key = None
            alts = self._plausible_alternatives_from_groups(claimed_compatible, best)
        else:
            linked_group = group
            messy_key = best.get("messy_key")
            alts = self._plausible_alternatives_from_groups(compatible, best)

        signals = dict(best["signals"])
        margin = None
        if second:
            margin = round(float(best["confidence"]) - float(second["confidence"]), 2)
        signals["top2_margin"] = margin
        audit = self._audit_block(
            headline=headline,
            why=summary,
            identity_status=status,
            validation=validation,
            alternatives=alts,
            master_candidate=template.get("candidate_name"),
            master_client=template.get("client_name"),
            client_candidate=(linked_group or {}).get("candidate_name"),
            client_client=(linked_group or {}).get("client_name"),
            candidate_similarity=float(signals.get("name_score") or 0),
            client_similarity=float(signals.get("client_score") or 0)
            if signals.get("client_available")
            else None,
            final_confidence=float(best["confidence"]),
        )
        explanation = {
            "identity_summary": summary,
            "identity_headline": headline,
            "signals": signals,
            "alternatives": alts,
            "identity_flags": flags,
            "match_breakdown": {
                "name_features": signals.get("name_features") or {},
                "client_score": signals.get("client_score"),
                "month_score": signals.get("month_score"),
                "top2_margin": margin,
                "homonym_count": template.get("_homonym_count"),
                "homonym_same_client": template.get("_homonym_same_client"),
            },
            "decision": {
                "name_band": signals.get("name_band"),
                "client_band": signals.get("client_band"),
                "status": status,
                "reason": summary,
            },
            "chosen": {
                "candidate_id": template.get("candidate_id"),
                "candidate_name": template.get("candidate_name"),
                "client_name": template.get("client_name"),
                "confidence": best["confidence"],
                "method": best["method"],
                "why": best.get("why_suggested"),
                "source_name": (linked_group or {}).get("candidate_name"),
            }
            if linked_group is not None
            else None,
            "validation": validation,
            "audit": audit,
        }

        if status == "unmatched" or identity_already_assigned:
            hours_out = 0
            weekly = {}
            monthly_hours = {}
            weekly_by_month = {}
            cumulative_hours = 0
            hours_note = ""

        return {
            **base_fields,
            "messy_name_original": (linked_group or {}).get("candidate_name"),
            "messy_client_name": (linked_group or {}).get("client_name"),
            "weekly_breakdown": weekly,
            "total_hours": hours_out,
            "cumulative_hours": cumulative_hours,
            "monthly_hours": monthly_hours,
            "weekly_by_month": weekly_by_month,
            "hours_note": hours_note,
            "confidence_score": best["confidence"] if linked_group is not None else 0.0,
            "match_method": best["method"] if linked_group is not None else "none",
            "match_status": status,
            "match_explanation": explanation,
            "alternatives": alts,
            "_messy_key": messy_key,
        }

    def _plausible_alternatives_from_groups(
        self,
        ranked: List[Dict[str, Any]],
        best: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Surface other messy identities that could also be this template person."""
        if not best:
            return []
        top_name = float(best["signals"].get("name_score") or 0)
        floor = max(self.MIN_IDENTITY_NAME_SCORE, top_name * self.ALT_RELATIVE_FLOOR)
        alts = []
        for r in ranked:
            group = r.get("group") or {}
            if group is (best.get("group") or {}):
                continue
            if r.get("messy_key") == best.get("messy_key"):
                continue
            if not r.get("identity_compatible"):
                continue
            name_score = float(r["signals"].get("name_score") or 0)
            if name_score < floor:
                continue
            why = r.get("why_suggested") or ""
            alts.append({
                "candidate_id": None,
                "candidate_name": group.get("candidate_name"),
                "client_name": group.get("client_name"),
                "confidence": r["confidence"],
                "name_score": name_score,
                "client_score": float(r["signals"].get("client_score") or 0),
                "combined_score": r["confidence"],
                "method": r["method"],
                "why_suggested": why,
                "why": why,
            })
            if len(alts) >= 4:
                break
        return alts

    def rank_for_rematch(
        self,
        messy_name: str,
        template_candidates: List[Dict[str, Any]],
        messy_client: Optional[str] = None,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """Rank reference candidates for manual rematch UI (identity-first)."""
        group = {"candidate_name": messy_name, "client_name": messy_client or ""}
        templates = []
        for t in template_candidates:
            parsed = parse_name_tokens(t.get("candidate_name"))
            templates.append({
                **t,
                "_norm_name": parsed["normalized"],
                "_name_parts": parsed,
                "_norm_client": normalize_client_name(t.get("client_name")),
                "_month": normalize_month_year(str(t.get("month") or "")),
                "_candidate_id": str(t.get("candidate_id") or "").strip().upper(),
            })
        ranked = self._rank_templates(group, templates, "")
        out = []
        for r in ranked:
            if not r.get("identity_compatible") and r["confidence"] < self.REVIEW_THRESHOLD:
                continue
            cand = r["candidate"]
            out.append({
                "id": cand.get("id"),
                "candidate_id": cand.get("candidate_id"),
                "candidate_name": cand.get("candidate_name"),
                "client_name": cand.get("client_name"),
                "month": cand.get("month"),
                "confidence": r["confidence"],
                "identity_compatible": r.get("identity_compatible", False),
                "why_suggested": r.get("why_suggested") or "",
                "method": r.get("method"),
            })
            if len(out) >= limit:
                break
        return out

    def _rank_templates(
        self,
        group: Dict[str, Any],
        templates: List[Dict[str, Any]],
        target_month: str,
        *,
        by_norm: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        by_last: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        name_choices: Optional[List[str]] = None,
        name_to_templates: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Rank templates for one client person.

        Performance: do NOT score every template. Build a small candidate pool via
        exact-name / last-name blocking + RapidFuzz extract, then fully score that pool.
        """
        messy_name = group.get("candidate_name") or ""
        messy_parts = parse_name_tokens(messy_name)
        messy_norm = messy_parts["normalized"]
        pool: Dict[Any, Dict[str, Any]] = {}

        def _add(rows: List[Dict[str, Any]]) -> None:
            for t in rows:
                key = t.get("id")
                if key is None:
                    key = id(t)
                pool[key] = t

        # 1) Exact normalized name
        if by_norm and messy_norm:
            _add(by_norm.get(messy_norm, []))

        # 2) Same last-name block (cheap, high recall for identity)
        last = messy_parts.get("last") or ""
        if by_last and last:
            _add(by_last.get(last, []))

        # 3) RapidFuzz top-N over template names (C-accelerated) when pool is thin
        if name_choices is not None and name_to_templates is not None and len(pool) < 25 and messy_norm:
            from rapidfuzz import process

            hits = process.extract(
                messy_norm,
                name_choices,
                scorer=fuzz.token_set_ratio,
                limit=40,
                score_cutoff=65,
            )
            for choice, _score, _idx in hits:
                _add(name_to_templates.get(choice, []))

        candidates = list(pool.values()) if pool else templates
        # Safety cap: never fully score more than 80 templates per person
        if len(candidates) > 80 and name_choices is not None and name_to_templates is not None:
            from rapidfuzz import process

            hits = process.extract(
                messy_norm,
                name_choices,
                scorer=fuzz.WRatio,
                limit=80,
                score_cutoff=55,
            )
            trimmed: Dict[Any, Dict[str, Any]] = {}
            for choice, _score, _idx in hits:
                for t in name_to_templates.get(choice, []):
                    trimmed[t.get("id", id(t))] = t
            if trimmed:
                candidates = list(trimmed.values())

        ranked = [
            self._score_pair(group, t, target_month, messy_parts=messy_parts)
            for t in candidates
        ]
        ranked.sort(
            key=lambda x: (x["identity_compatible"], x["confidence"], x["signals"]["name_score"]),
            reverse=True,
        )
        return ranked

    def _score_pair(
        self,
        group: Dict[str, Any],
        template: Dict[str, Any],
        target_month: str,
        messy_parts: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        messy_name = group.get("candidate_name") or ""
        template_name = template.get("candidate_name") or ""

        name_info = self._name_identity(
            messy_name,
            template_name,
            messy_parts=messy_parts,
            template_parts=template.get("_name_parts"),
        )
        name_score = name_info["score"]
        identity_ok = name_info["compatible"]

        client_available = bool(
            normalize_client_name(group.get("client_name"))
            and template.get("_norm_client")
        )
        if client_available:
            client_score = float(
                self.scorer.client_similarity(group.get("client_name"), template.get("client_name"))
            )
            # Soft boost when one normalized client string contains the other
            c1 = normalize_client_name(group.get("client_name"))
            c2 = template.get("_norm_client") or ""
            if c1 and c2 and (c1 in c2 or c2 in c1):
                client_score = max(client_score, 88.0)
        else:
            client_score = 0.0

        messy_month = normalize_month_year(str(group.get("month") or target_month or ""))
        template_month = template.get("_month") or target_month
        month_available = bool(messy_month and template_month)
        month_score = 100.0 if month_available and messy_month == template_month else 0.0

        # Combined confidence: name + client + month. Client can pull a strong
        # name match below auto-match when clients disagree. Never floor confidence
        # back up to name-only evidence.
        if not identity_ok:
            confidence = min(name_score * 0.55, self.REVIEW_THRESHOLD - 1.0)
            weights = {"name": 1.0, "client": 0.0, "month": 0.0}
        else:
            weights = {
                "name": self.WEIGHT_NAME,
                "client": self.WEIGHT_CLIENT if client_available else 0.0,
                "month": self.WEIGHT_MONTH if month_available else 0.0,
            }
            total_w = sum(weights.values()) or 1.0
            for k in weights:
                weights[k] /= total_w
            confidence = (
                name_score * weights["name"]
                + client_score * weights["client"]
                + month_score * weights["month"]
            )

        id_match = False
        messy_id = str(group.get("candidate_id") or "").strip().upper()
        if messy_id and template.get("_candidate_id") and messy_id == template["_candidate_id"]:
            id_match = True
            confidence = min(100.0, confidence + 8.0)
            identity_ok = True

        invoice_score, invoice_why = self._invoice_prefix_signal(
            group.get("invoice_prefixes") or [],
            template.get("_name_parts") or parse_name_tokens(template_name),
        )
        if identity_ok and invoice_score >= 90:
            confidence = min(100.0, confidence + 4.0)
            name_info["evidence"] = list(name_info.get("evidence") or []) + ["invoice_prefix_corroborates"]
            if invoice_why:
                why_base = (name_info.get("why") or "").rstrip(".")
                name_info["why"] = f"{why_base}. {invoice_why}" if why_base else invoice_why

        client_band = self._client_band(client_score, client_available)
        name_band = self._name_band(name_score, identity_ok)

        return {
            "candidate": template,
            "confidence": round(float(confidence), 2),
            "method": name_info["method"] + ("+id" if id_match else "") + ("+invoice" if invoice_score >= 90 else ""),
            "identity_compatible": identity_ok,
            "why_suggested": name_info["why"],
            "signals": {
                "name_score": round(name_score, 2),
                "client_score": round(client_score, 2),
                "month_score": round(month_score, 2),
                "invoice_score": round(invoice_score, 2),
                "identity_compatible": identity_ok,
                "identity_evidence": name_info["evidence"],
                "client_available": client_available,
                "month_available": month_available,
                "id_match": id_match,
                "client_band": client_band,
                "name_band": name_band,
                "weights": {k: round(v, 4) for k, v in weights.items()},
                "messy_month": messy_month,
                "template_month": template_month,
                "messy_client": group.get("client_name"),
                "template_client": template.get("client_name"),
                "messy_candidate": messy_name,
                "template_candidate": template_name,
                "name_features": name_info.get("features") or {},
                "master_name_not_unique": int(template.get("_homonym_same_client") or 1) > 1,
                "homonym_count": int(template.get("_homonym_count") or 1),
                "homonym_same_client": int(template.get("_homonym_same_client") or 1),
            },
        }

    @staticmethod
    def _invoice_prefix_signal(
        prefixes: List[Any],
        name_parts: Dict[str, Any],
    ) -> Tuple[float, str]:
        """
        Weak corroboration: invoice codes like GANT-06/07 often start with
        letters from the person's name. Never used as sole identity evidence.
        """
        cleaned = [str(p).strip().upper() for p in (prefixes or []) if str(p).strip()]
        if not cleaned:
            return 0.0, ""
        first = str(name_parts.get("first") or "").upper()
        last = str(name_parts.get("last") or "").upper()
        tokens = [str(t).upper() for t in (name_parts.get("tokens") or [])]
        for prefix in cleaned:
            if len(prefix) < 3:
                continue
            if last and last.startswith(prefix):
                return 100.0, "Invoice code prefix matches last name"
            if first and first.startswith(prefix):
                return 95.0, "Invoice code prefix matches first name"
            if any(
                token.startswith(prefix) or prefix.startswith(token[:4])
                for token in tokens
                if len(token) >= 3
            ):
                return 90.0, "Invoice code prefix matches a name token"
        return 0.0, ""

    def _client_band(self, client_score: float, client_available: bool) -> str:
        if not client_available:
            return "unavailable"
        if client_score >= self.CLIENT_COMPAT_STRONG:
            return "strong"
        if client_score >= self.CLIENT_COMPAT_MODERATE:
            return "moderate"
        if client_score <= self.CLIENT_CONFLICT_MAX:
            return "conflict"
        return "weak"

    def _name_band(self, name_score: float, identity_ok: bool) -> str:
        if not identity_ok or name_score < self.MIN_IDENTITY_NAME_SCORE:
            return "insufficient"
        if name_score >= self.STRONG_NAME_SCORE:
            return "strong"
        if name_score >= self.MODERATE_NAME_SCORE:
            return "moderate"
        return "weak"

    def _name_identity(
        self,
        messy: str,
        template: str,
        messy_parts: Optional[Dict[str, Any]] = None,
        template_parts: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        p1 = messy_parts or parse_name_tokens(messy)
        p2 = template_parts or parse_name_tokens(template)
        n1, n2 = p1["normalized"], p2["normalized"]
        evidence: List[str] = []

        if not n1 or not n2:
            return {
                "score": 0.0,
                "compatible": False,
                "method": "empty",
                "why": "Missing name",
                "evidence": evidence,
                "features": {},
            }

        if n1 == n2:
            evidence.append("exact_normalized_name")
            features = name_feature_scores(messy, template, p1, p2)
            return {
                "score": 100.0,
                "compatible": True,
                "method": "exact",
                "why": "Normalized full name matches exactly",
                "evidence": evidence,
                "features": features,
            }

        compact1 = str(p1.get("compact") or "")
        compact2 = str(p2.get("compact") or "")
        if compact1 and compact1 == compact2:
            evidence.append("compact_name_match")
            features = name_feature_scores(messy, template, p1, p2)
            return {
                "score": 99.5,
                "compatible": True,
                "method": "compact",
                "why": "Names match after removing punctuation and spaces",
                "evidence": evidence,
                "features": features,
            }

        # Token-order insensitive equality (handles First Last vs Last First after normalize)
        if sorted(p1["tokens"]) == sorted(p2["tokens"]) and p1["tokens"]:
            evidence.append("same_tokens_any_order")
            features = name_feature_scores(messy, template, p1, p2)
            return {
                "score": 99.0,
                "compatible": True,
                "method": "token_permutation",
                "why": "Same name tokens in different order",
                "evidence": evidence,
                "features": features,
            }

        first_ok, first_why = self._token_compatible(p1["first"], p2["first"], "first")
        last_ok, last_why = self._token_compatible(p1["last"], p2["last"], "last")

        # Middle/initial compatibility (optional signal)
        middle_note = self._middle_note(p1, p2)

        # Shared significant tokens (length > 1)
        sig1 = {t for t in p1["tokens"] if len(t) > 1}
        sig2 = {t for t in p2["tokens"] if len(t) > 1}
        shared = sig1 & sig2
        coverage = (len(shared) / max(len(sig1), 1)) if sig1 else 0.0

        compatible = False
        method = "fuzzy"
        why_parts: List[str] = []

        if first_ok and last_ok:
            compatible = True
            evidence.extend([first_why, last_why])
            why_parts.append(self._human_token_reason(first_why, last_why, middle_note))
            method = "first_last"
            if "initial" in first_why or "initial" in last_why:
                method = "initial_variant"
        elif last_ok and coverage >= 0.5 and first_ok is False:
            # Last name matches but first does not — not the same person
            compatible = False
            evidence.append(last_why)
            evidence.append("first_name_not_compatible")
        elif first_ok and last_ok is False and self._initial_match(p1["last"], p2["last"]):
            compatible = True
            evidence.extend([first_why, "last_initial_compatible"])
            why_parts.append(
                self._human_token_reason(first_why, "last_initial", middle_note)
            )
            method = "first_last_initial"
        elif n1 in n2 or n2 in n1:
            # Containment only if both first+last evidence soft-pass via tokens
            if last_ok or self._initial_match(p1["last"], p2["last"]):
                if first_ok or self._initial_match(p1["first"], p2["first"]):
                    compatible = True
                    evidence.append("name_containment")
                    base = "One name is a formatted/abbreviated form of the other"
                    why_parts.append(f"{base}. {middle_note}" if middle_note else base)
                    method = "containment"

        if not compatible and first_ok:
            sig1 = {t for t in p1["tokens"] if len(t) > 1}
            sig2 = {t for t in p2["tokens"] if len(t) > 1}
            shared = sig1 & sig2
            shorter, longer = (sig1, sig2) if len(sig1) <= len(sig2) else (sig2, sig1)
            shorter_last = p1["last"] if len(sig1) <= len(sig2) else p2["last"]
            if (
                len(shared) >= 2
                and shorter
                and shorter <= longer
                and shorter_last in longer
            ):
                compatible = True
                evidence.append("token_subset")
                why_parts.append(
                    "All significant tokens of the shorter name appear in the longer name"
                )
                method = "token_subset"

        # Score: blend identity-aware components; skip expensive metaphone path when possible
        first_score = float(fuzz.ratio(p1["first"], p2["first"])) if p1["first"] and p2["first"] else 0.0
        if self._initial_match(p1["first"], p2["first"]):
            first_score = max(first_score, 92.0)
        last_score = float(fuzz.ratio(p1["last"], p2["last"])) if p1["last"] and p2["last"] else 0.0
        if self._initial_match(p1["last"], p2["last"]):
            last_score = max(last_score, 92.0)

        token_set = float(fuzz.token_set_ratio(n1, n2))
        token_sort = float(fuzz.token_sort_ratio(n1, n2))
        # Lightweight stand-in for full SimilarityScorer (avoids metaphone on every pair)
        raw = float(fuzz.WRatio(n1, n2))

        features = name_feature_scores(messy, template, p1, p2)
        jaro = float(features.get("name_jaro_similarity") or 0)
        ngram = float(features.get("name_ngram_similarity") or 0)

        identity_blend = (
            last_score * 0.36
            + first_score * 0.26
            + token_set * 0.12
            + token_sort * 0.08
            + raw * 0.04
            + jaro * 0.08
            + ngram * 0.06
        )

        if middle_note:
            evidence.append("middle_differs_or_matches")

        if not compatible:
            # Guardrail: unrelated high fuzzy strings must not look like identities
            score = min(identity_blend * 0.65, 60.0)
            why = "Name tokens are not identity-compatible with this reference candidate"
            return {
                "score": round(score, 2),
                "compatible": False,
                "method": "rejected_unrelated",
                "why": why,
                "evidence": evidence,
                "features": features,
            }

        score = min(100.0, max(identity_blend, 78.0 if first_ok and last_ok else identity_blend))
        if method == "exact":
            score = 100.0

        why = "; ".join([p for p in why_parts if p]) or "Compatible first/last name evidence"
        return {
            "score": round(score, 2),
            "compatible": True,
            "method": method,
            "why": why,
            "evidence": evidence,
            "features": features,
        }

    def _token_compatible(self, a: str, b: str, role: str) -> Tuple[bool, str]:
        if not a or not b:
            return False, f"{role}_missing"
        if a == b:
            return True, f"{role}_exact"
        if self._initial_match(a, b):
            return True, f"{role}_initial"
        threshold = self.FIRST_NAME_FUZZY_MIN if role == "first" else self.LAST_NAME_FUZZY_MIN
        if float(fuzz.ratio(a, b)) >= threshold:
            return True, f"{role}_fuzzy"
        jaro = float(JaroWinkler.similarity(a, b) or 0)
        jaro_pct = jaro * 100.0 if jaro <= 1.0 else jaro
        jaro_min = 92.0 if role == "first" else 93.0
        if min(len(a), len(b)) >= 4 and jaro_pct >= jaro_min:
            return True, f"{role}_jaro"
        return False, f"{role}_mismatch"

    @staticmethod
    def _initial_match(a: str, b: str) -> bool:
        if not a or not b:
            return False
        if len(a) == 1 and b.startswith(a):
            return True
        if len(b) == 1 and a.startswith(b):
            return True
        return False

    @staticmethod
    def _middle_note(p1: Dict[str, Any], p2: Dict[str, Any]) -> str:
        m1 = set(p1.get("middle") or [])
        m2 = set(p2.get("middle") or [])
        if not m1 and not m2:
            return ""
        if m1 == m2:
            return "Middle name/initials also match"
        if m1 and not m2:
            return "Messy name includes middle token(s) not present on reference"
        if m2 and not m1:
            return "Reference includes middle token(s) not present in messy name"
        if m1 & m2:
            return "Some middle tokens overlap; others differ"
        return "Middle name/initials differ"

    @staticmethod
    def _human_token_reason(first_why: str, last_why: str, middle_note: str) -> str:
        bits = []
        if first_why == "first_exact":
            bits.append("first name matches")
        elif first_why == "first_initial":
            bits.append("first name matches as an initial/abbreviation")
        elif first_why == "first_fuzzy":
            bits.append("first name is highly similar")
        if last_why in ("last_exact",):
            bits.append("last name matches")
        elif last_why in ("last_initial", "last_initial_compatible"):
            bits.append("last name matches as an initial/abbreviation")
        elif last_why == "last_fuzzy":
            bits.append("last name is highly similar")
        text = "; ".join(bits)
        text = text[:1].upper() + text[1:] if text else "Compatible name tokens"
        if middle_note:
            text = f"{text}. {middle_note}"
        return text

    def _plausible_alternatives(
        self,
        ranked: List[Dict[str, Any]],
        best: Dict[str, Any],
        exclude_id: Any = None,
    ) -> List[Dict[str, Any]]:
        """Only identity-compatible, near-top, non-conflicting alternatives."""
        if not best:
            return []
        top_name = float(best["signals"].get("name_score") or 0)
        floor = max(self.MIN_IDENTITY_NAME_SCORE, top_name * self.ALT_RELATIVE_FLOOR)
        top_client_avail = bool(best["signals"].get("client_available"))
        alts = []
        for r in ranked:
            cand = r["candidate"]
            if exclude_id is not None and cand.get("id") == exclude_id:
                continue
            if not r.get("identity_compatible"):
                continue
            name_score = float(r["signals"].get("name_score") or 0)
            if name_score < floor:
                continue
            client_score = float(r["signals"].get("client_score") or 0)
            client_available = bool(r["signals"].get("client_available"))
            # Do not surface alternatives whose client clearly conflicts when the
            # top candidate also has client evidence available.
            if top_client_avail and client_available and client_score <= self.CLIENT_CONFLICT_MAX:
                continue
            if (
                top_client_avail
                and client_available
                and client_score < self.ALT_MIN_CLIENT_WHEN_TOP_HAS_CLIENT
            ):
                continue
            why = r.get("why_suggested") or ""
            client_band = r["signals"].get("client_band")
            if client_available:
                why = (
                    f"{why}. Client similarity {client_score:.0f}% ({client_band})."
                    if why
                    else f"Client similarity {client_score:.0f}% ({client_band})."
                )
            alts.append({
                "candidate_id": cand.get("candidate_id"),
                "candidate_name": cand.get("candidate_name"),
                "client_name": cand.get("client_name"),
                "confidence": r["confidence"],
                "name_score": name_score,
                "client_score": client_score,
                "combined_score": r["confidence"],
                "method": r["method"],
                "why_suggested": why,
                "why": why,
                "signals": {
                    "name_score": name_score,
                    "client_score": client_score,
                    "client_band": client_band,
                    "identity_evidence": r["signals"].get("identity_evidence"),
                },
            })
            if len(alts) >= 4:
                break
        return alts

    def _hours_validation(self, hours: float) -> Dict[str, Any]:
        """Separate business/hours validation — does not decide identity."""
        cap = self.HOURS_VALIDATION_CAP
        if hours <= 0:
            return {
                "status": "no_hours",
                "summary": "No positive hours were mapped from the client file for this row.",
                "cap": cap,
                "hours": hours,
            }
        if hours > cap:
            return {
                "status": "requires_validation",
                "summary": (
                    f"{hours:.0f}h recorded for the cycle month exceeds the configured "
                    f"validation cap ({cap:.0f}h). Identity is separate — Accounts should "
                    f"validate hours only."
                ),
                "cap": cap,
                "hours": hours,
            }
        return {
            "status": "ok",
            "summary": f"{hours:.0f}h recorded for the cycle month (within configured cap {cap:.0f}h).",
            "cap": cap,
            "hours": hours,
        }

    @staticmethod
    def _audit_block(
        headline: str,
        why: str,
        identity_status: str,
        validation: Optional[Dict[str, Any]] = None,
        alternatives: Optional[List[Dict[str, Any]]] = None,
        *,
        master_candidate: Optional[str] = None,
        master_client: Optional[str] = None,
        client_candidate: Optional[str] = None,
        client_client: Optional[str] = None,
        candidate_similarity: Optional[float] = None,
        client_similarity: Optional[float] = None,
        final_confidence: Optional[float] = None,
    ) -> Dict[str, Any]:
        return {
            "what_happened": headline,
            "why": why,
            "identity_status": identity_status,
            "validation_status": (validation or {}).get("status"),
            "validation_summary": (validation or {}).get("summary"),
            "has_alternatives": bool(alternatives),
            "master_candidate": master_candidate,
            "master_client": master_client,
            "client_candidate": client_candidate,
            "client_client": client_client,
            "candidate_similarity": candidate_similarity,
            "client_similarity": client_similarity,
            "final_confidence": final_confidence,
            "status": identity_status,
            "reason": why,
        }

    def _decide_status(
        self,
        group: Dict[str, Any],
        best: Dict[str, Any],
        second: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Apply the candidate+client decision matrix.

        Returns status, summary, headline, flags.
        """
        signals = best["signals"]
        name_score = float(signals.get("name_score") or 0)
        client_score = float(signals.get("client_score") or 0)
        client_available = bool(signals.get("client_available"))
        identity_ok = bool(best.get("identity_compatible"))
        confidence = float(best.get("confidence") or 0)
        id_match = bool(signals.get("id_match"))
        name_band = signals.get("name_band") or self._name_band(name_score, identity_ok)
        client_band = signals.get("client_band") or self._client_band(
            client_score, client_available
        )

        cand = best["candidate"]
        master_name = cand.get("candidate_name")
        master_client = cand.get("client_name")
        client_name = group.get("candidate_name")
        client_client = group.get("client_name")

        # Case F/G — weak / no candidate identity
        if not identity_ok or name_score < self.MIN_IDENTITY_NAME_SCORE:
            return {
                "status": "unmatched",
                "summary": "No sufficiently reliable candidate identity was found.",
                "headline": "Unmatched",
                "flags": ["weak_or_missing_candidate_identity"],
            }

        # Case D — strong candidate + strong conflicting client
        if (
            name_band == "strong"
            and client_available
            and client_band == "conflict"
        ):
            return {
                "status": "conflicting",
                "summary": (
                    "Candidate identity is strong, but client identity conflicts with the "
                    f"master client. Master client '{master_client or '—'}' vs client file "
                    f"'{client_client or '—'}'."
                ),
                "headline": f"Conflict: {master_name}",
                "flags": ["client_mismatch_with_strong_name"],
            }

        # Case E — close second candidate
        ambiguous = bool(
            second
            and second.get("identity_compatible")
            and (best["confidence"] - second["confidence"]) < self.AMBIGUITY_GAP
            and float(second["signals"].get("name_score") or 0) >= self.MIN_IDENTITY_NAME_SCORE
        )
        if ambiguous and second:
            other = second["candidate"].get("candidate_name")
            other_client = second["candidate"].get("client_name")
            other_client_band = second["signals"].get("client_band")
            # Contradictory client evidence between top two → conflict
            if (
                client_available
                and second["signals"].get("client_available")
                and client_band in ("strong", "moderate")
                and other_client_band in ("strong", "moderate")
                and client_band != other_client_band
            ) or (
                client_available
                and second["signals"].get("client_available")
                and abs(client_score - float(second["signals"].get("client_score") or 0)) >= 35
                and min(client_score, float(second["signals"].get("client_score") or 0))
                <= self.CLIENT_COMPAT_MODERATE
            ):
                return {
                    "status": "conflicting",
                    "summary": (
                        f"Multiple reference candidates are similarly plausible for "
                        f"'{client_name}' with contradictory client evidence "
                        f"('{master_name}' / '{master_client}' vs '{other}' / '{other_client}')."
                    ),
                    "headline": f"Conflict: ambiguous between {master_name} and {other}",
                    "flags": ["ambiguous_top_candidates", "contradictory_client_evidence"],
                }
            return {
                "status": "needs_review",
                "summary": (
                    f"Two reference candidates are highly similar to '{client_name}': "
                    f"'{master_name}' ({best['confidence']}%) and "
                    f"'{other}' ({second['confidence']}%). Confirm which person is correct."
                ),
                "headline": f"Needs review: ambiguous between {master_name} and {other}",
                "flags": ["ambiguous_top_candidates"],
            }

        # Exact Candidate ID anchor (when present on both sides)
        if id_match and not (client_available and client_band == "conflict"):
            if (not client_available) or client_band in ("strong", "moderate"):
                return {
                    "status": "matched",
                    "summary": (
                        "Candidate ID matches exactly"
                        + (
                            " and client name is compatible."
                            if client_available and client_band == "strong"
                            else (
                                " with moderate client evidence."
                                if client_available
                                else "; client evidence was incomplete but ID is authoritative."
                            )
                        )
                    ),
                    "headline": f"Matched: {master_name}",
                    "flags": ["exact_candidate_id"],
                }
            return {
                "status": "needs_review",
                "summary": (
                    "Candidate ID matches, but client evidence is weak. Confirm before accepting."
                ),
                "headline": f"Needs review: {master_name}",
                "flags": ["exact_candidate_id", "weak_client_with_id"],
            }

        # Case A — strong candidate + strong compatible client
        if name_band == "strong" and client_available and client_band == "strong":
            return {
                "status": "matched",
                "summary": (
                    "Candidate name strongly matches and client name is compatible."
                ),
                "headline": f"Matched: {master_name}",
                "flags": [],
            }

        # Case B — strong candidate + moderate client
        if name_band == "strong" and client_available and client_band == "moderate":
            return {
                "status": "needs_review",
                "summary": (
                    "Candidate name is strong, but client evidence is only moderately "
                    "compatible. Confirm client identity before accepting."
                ),
                "headline": f"Needs review: {master_name}",
                "flags": ["strong_name_moderate_client"],
            }

        # Case B/incomplete — strong name but client missing
        if name_band == "strong" and not client_available:
            return {
                "status": "needs_review",
                "summary": (
                    "Candidate name is plausible but client evidence is insufficient "
                    "for automatic confirmation."
                ),
                "headline": f"Needs review: {master_name}",
                "flags": ["strong_name_missing_client"],
            }

        # Strong name + weak (non-conflict) client
        if name_band == "strong" and client_available and client_band == "weak":
            return {
                "status": "needs_review",
                "summary": (
                    "Candidate name is strong, but client evidence is weak. "
                    "Human confirmation required."
                ),
                "headline": f"Needs review: {master_name}",
                "flags": ["strong_name_weak_client"],
            }

        # Case C — moderate candidate + strong compatible client
        if name_band == "moderate" and client_available and client_band == "strong":
            return {
                "status": "needs_review",
                "summary": (
                    "Client name is strongly compatible, but candidate name evidence is "
                    "only moderate. Confirm the person before accepting."
                ),
                "headline": f"Needs review: {master_name}",
                "flags": ["moderate_name_strong_client"],
            }

        # Moderate + moderate / other mid-band → review if above review threshold
        if (
            identity_ok
            and name_score >= self.MIN_IDENTITY_NAME_SCORE
            and confidence >= self.REVIEW_THRESHOLD
        ):
            return {
                "status": "needs_review",
                "summary": (
                    f"Possible match to '{master_name}' "
                    f"({confidence}% combined confidence; name {name_score:.0f}%, "
                    f"client {client_score:.0f}%{' unavailable' if not client_available else ''}). "
                    f"{best.get('why_suggested') or 'Confirm before accepting.'}"
                ),
                "headline": f"Needs review: {master_name}",
                "flags": ["medium_identity_confidence"],
            }

        # Below review floor → unmatched (do not force closest fuzzy result)
        return {
            "status": "unmatched",
            "summary": "No sufficiently reliable candidate identity was found.",
            "headline": "Unmatched",
            "flags": ["below_review_threshold"],
        }

    def _build_match_record(
        self,
        group: Dict[str, Any],
        ranked: List[Dict[str, Any]],
        assigned_template_ids: set,
        target_month: str,
    ) -> Dict[str, Any]:
        # Prefer unassigned, identity-compatible candidates for auto-linking
        available = [
            r for r in ranked
            if r["candidate"]["id"] not in assigned_template_ids and r.get("identity_compatible")
        ]
        # Fallback: any unassigned ranked row (still may be unmatched if weak)
        if not available:
            available = [r for r in ranked if r["candidate"]["id"] not in assigned_template_ids]

        best_unassigned = available[0] if available else None
        # Overall best identity match (may already be claimed by another client identity)
        overall_compatible = [r for r in ranked if r.get("identity_compatible")]
        best_overall = overall_compatible[0] if overall_compatible else best_unassigned

        # Ambiguity among unassigned identity-compatible competitors
        compatible_pool = [r for r in available if r.get("identity_compatible")]
        second = compatible_pool[1] if len(compatible_pool) > 1 else None

        total_hours = float(group.get("total_hours") or 0)
        hours_out = int(round(total_hours))
        weekly = group.get("weekly_breakdown") or {}
        cumulative_hours = float(group.get("cumulative_hours") or total_hours)
        monthly_hours = group.get("monthly_hours") or {}
        weekly_by_month = group.get("weekly_by_month") or {}
        hours_note = group.get("hours_note") or ""
        validation = self._hours_validation(hours_out)

        base_fields = {
            "messy_name_original": group.get("candidate_name"),
            "messy_client_name": group.get("client_name"),
            "messy_month": group.get("month") or target_month,
            "weekly_records": group.get("source_rows") or [],
            "weekly_breakdown": weekly,
            "total_hours": hours_out,
            "cumulative_hours": cumulative_hours,
            "monthly_hours": monthly_hours,
            "weekly_by_month": weekly_by_month,
            "hours_note": hours_note,
            "validation_status": validation["status"],
        }

        if not best_overall and not best_unassigned:
            summary = "No sufficiently reliable candidate identity was found."
            explanation = {
                "identity_summary": summary,
                "identity_headline": "Unmatched",
                "signals": {},
                "alternatives": [],
                "identity_flags": ["no_candidates"],
                "validation": validation,
                "audit": self._audit_block(
                    headline="Unmatched",
                    why=summary,
                    identity_status="unmatched",
                    validation=validation,
                    client_candidate=group.get("candidate_name"),
                    client_client=group.get("client_name"),
                    final_confidence=0.0,
                ),
            }
            return {
                **base_fields,
                "template_candidate": None,
                "template_candidate_id": None,
                "template_candidate_name": None,
                "template_candidate_id_str": None,
                "confidence_score": 0.0,
                "match_method": "none",
                "match_status": "unmatched",
                "match_explanation": explanation,
                "alternatives": [],
            }

        # If the only strong identity is already claimed, classify against that
        # overall match (conflict / duplicate / review) instead of forcing unmatched.
        best = best_unassigned
        already_claimed = False
        if (
            best_overall
            and best_overall.get("identity_compatible")
            and (
                not best_unassigned
                or not best_unassigned.get("identity_compatible")
                or float(best_unassigned["signals"].get("name_score") or 0)
                < float(best_overall["signals"].get("name_score") or 0) - 5
            )
            and best_overall["candidate"]["id"] in assigned_template_ids
        ):
            best = best_overall
            already_claimed = True
            second = None

        if not best:
            best = best_overall

        decision = self._decide_status(group, best, second)
        status = decision["status"]
        summary = decision["summary"]
        headline = decision["headline"]
        flags = list(decision["flags"])

        if already_claimed and status in ("matched", "needs_review"):
            # Another client-side identity already owns this master candidate.
            if status == "matched" or (
                best["signals"].get("name_band") == "strong"
                and best["signals"].get("client_band") == "strong"
            ):
                status = "potential_duplicate"
                summary = (
                    "Multiple client-side identities appear to claim the same master "
                    f"candidate. '{best['candidate'].get('candidate_name')}' is already "
                    "linked to another client-side identity."
                )
                headline = f"Potential duplicate: {best['candidate'].get('candidate_name')}"
                flags.append("template_already_claimed")
            else:
                flags.append("template_already_claimed")
                summary = (
                    f"{summary} Another client-side identity already claims this master "
                    "candidate."
                )

        # Strong name + conflicting client against an already-claimed master still conflicts
        if (
            already_claimed
            and best.get("identity_compatible")
            and float(best["signals"].get("name_score") or 0) >= self.STRONG_NAME_SCORE
            and best["signals"].get("client_available")
            and float(best["signals"].get("client_score") or 0) <= self.CLIENT_CONFLICT_MAX
        ):
            status = "conflicting"
            summary = (
                "Candidate identity is strong, but client identity conflicts with the "
                "master client."
            )
            headline = f"Conflict: {best['candidate'].get('candidate_name')}"
            flags = ["client_mismatch_with_strong_name", "template_already_claimed"]

        cand = best["candidate"]
        alts = self._plausible_alternatives(
            compatible_pool if compatible_pool else overall_compatible,
            best,
            exclude_id=cand.get("id"),
        )

        # Unmatched: do not keep a linked template
        if status == "unmatched":
            linked = None
            alts = self._plausible_alternatives(
                overall_compatible,
                best if best.get("identity_compatible") else (
                    next((r for r in overall_compatible), best)
                ),
            )
        else:
            linked = cand

        signals = dict(best["signals"])
        audit = self._audit_block(
            headline=headline,
            why=summary,
            identity_status=status,
            validation=validation,
            alternatives=alts,
            master_candidate=(linked or cand).get("candidate_name"),
            master_client=(linked or cand).get("client_name"),
            client_candidate=group.get("candidate_name"),
            client_client=group.get("client_name"),
            candidate_similarity=float(signals.get("name_score") or 0),
            client_similarity=float(signals.get("client_score") or 0)
            if signals.get("client_available")
            else None,
            final_confidence=float(best["confidence"]),
        )

        explanation = {
            "identity_summary": summary,
            "identity_headline": headline,
            "signals": signals,
            "alternatives": alts,
            "identity_flags": flags,
            "decision": {
                "name_band": signals.get("name_band"),
                "client_band": signals.get("client_band"),
                "status": status,
                "reason": summary,
                "already_claimed": already_claimed,
            },
            "chosen": {
                "candidate_id": (linked or {}).get("candidate_id") if linked else None,
                "candidate_name": (linked or {}).get("candidate_name") if linked else None,
                "client_name": (linked or {}).get("client_name") if linked else None,
                "confidence": best["confidence"],
                "method": best["method"],
                "why": best.get("why_suggested"),
            }
            if linked
            else None,
            "validation": validation,
            "audit": audit,
        }

        return {
            **base_fields,
            "template_candidate": linked,
            "template_candidate_id": linked.get("id") if linked else None,
            "template_candidate_name": linked.get("candidate_name") if linked else None,
            "template_candidate_id_str": linked.get("candidate_id") if linked else None,
            "confidence_score": best["confidence"]
            if linked or best.get("identity_compatible")
            else 0.0,
            "match_method": best["method"]
            if linked or best.get("identity_compatible")
            else "none",
            "match_status": status,
            "match_explanation": explanation,
            "alternatives": alts,
        }
