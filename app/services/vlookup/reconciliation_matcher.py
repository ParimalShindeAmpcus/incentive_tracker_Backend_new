"""
Identity-first candidate matching for Hours Template vs client hours.

Design principles:
- Name identity is the primary signal (not generic string similarity alone)
- Alternatives only include identity-compatible reference candidates
- Ambiguity is relative among plausible name variants
- Hours/business validation is separate from identity status
- No person/client-specific hardcoded cases
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from rapidfuzz import fuzz

from app.config import get_settings

def _settings():
    return get_settings()

from app.services.vlookup.normalization import (
    normalize_client_name,
    normalize_month_year,
    normalize_name,
    parse_name_tokens,
)
from app.services.vlookup.similarity import SimilarityScorer


class ReconciliationMatcher:
    """Match messy client people to Hours Template reference candidates."""

    def __init__(
        self,
        auto_threshold: float = None,
        review_threshold: float = None,
        ambiguity_gap: float = None,
        hours_validation_cap: float = None,
    ):
        # Prefer settings when present; callers may override.
        self.AUTO_MATCH_THRESHOLD = float(
            auto_threshold if auto_threshold is not None
            else getattr(get_settings(), "THRESHOLD_AUTO_MATCH", getattr(get_settings(), "threshold_auto_match", 92.0))
        )
        # Settings historically used very high auto thresholds; for identity we
        # interpret AUTO as strong identity confidence and REVIEW as minimum.
        if self.AUTO_MATCH_THRESHOLD >= 99:
            self.AUTO_MATCH_THRESHOLD = 92.0

        self.REVIEW_THRESHOLD = float(
            review_threshold if review_threshold is not None
            else getattr(get_settings(), "THRESHOLD_REVIEW", getattr(get_settings(), "threshold_review", 80.0))
        )
        if self.REVIEW_THRESHOLD >= 95:
            self.REVIEW_THRESHOLD = 78.0

        self.AMBIGUITY_GAP = float(ambiguity_gap if ambiguity_gap is not None else 8.0)
        self.HOURS_VALIDATION_CAP = float(
            hours_validation_cap
            if hours_validation_cap is not None
            else getattr(get_settings(), "HOURS_VALIDATION_CAP", getattr(get_settings(), "hours_validation_cap", 160.0))
        )

        # Identity gates (relative/fuzzy, not person-specific)
        self.MIN_IDENTITY_NAME_SCORE = 70.0
        self.ALT_RELATIVE_FLOOR = 0.82  # alternative must be >= 82% of top name score
        self.LAST_NAME_FUZZY_MIN = 88.0
        self.FIRST_NAME_FUZZY_MIN = 85.0

        self.scorer = SimilarityScorer()

    def match(
        self,
        template_candidates: List[Dict[str, Any]],
        client_groups: List[Dict[str, Any]],
        target_month: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        target = normalize_month_year(target_month) if target_month else ""

        templates = []
        by_norm: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        by_last: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        name_to_templates: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for t in template_candidates:
            parsed = parse_name_tokens(t.get("candidate_name"))
            enriched = {
                **t,
                "_norm_name": parsed["normalized"],
                "_name_parts": parsed,
                "_norm_client": normalize_client_name(t.get("client_name")),
                "_month": normalize_month_year(str(t.get("month") or target or "")),
                "_candidate_id": str(t.get("candidate_id") or "").strip().upper(),
            }
            templates.append(enriched)
            if enriched["_norm_name"]:
                by_norm[enriched["_norm_name"]].append(enriched)
                name_to_templates[enriched["_norm_name"]].append(enriched)
            last = parsed.get("last") or ""
            if last:
                by_last[last].append(enriched)

        name_choices = list(name_to_templates.keys())

        scored_pairs = []
        for group in client_groups:
            ranked = self._rank_templates(
                group,
                templates,
                target,
                by_norm=by_norm,
                by_last=by_last,
                name_choices=name_choices,
                name_to_templates=name_to_templates,
            )
            scored_pairs.append({"group": group, "candidates": ranked})

        scored_pairs.sort(
            key=lambda p: (
                p["candidates"][0]["identity_compatible"],
                p["candidates"][0]["confidence"],
            ) if p["candidates"] else (False, -1),
            reverse=True,
        )

        assigned_template_ids = set()
        template_claims: Dict[Any, List[str]] = defaultdict(list)
        pending = []

        for pair in scored_pairs:
            record = self._build_match_record(
                pair["group"], pair["candidates"], assigned_template_ids, target
            )
            pending.append(record)
            tid = record.get("template_candidate_id")
            if tid is not None and record["match_status"] in ("matched", "needs_review"):
                assigned_template_ids.add(tid)
                template_claims[tid].append(record["messy_name_original"])

        results = {
            "matched": [],
            "needs_review": [],
            "unmatched": [],
            "potential_duplicate": [],
            "conflicting": [],
        }

        for record in pending:
            explanation = record.setdefault("match_explanation", {})
            hours = float(record.get("total_hours") or 0)
            cumulative = float(record.get("cumulative_hours") or hours)

            # Hours metadata — NEVER changes identity match_status
            explanation["cumulative_hours"] = cumulative
            explanation["monthly_hours"] = record.get("monthly_hours") or {}
            explanation["weekly_by_month"] = record.get("weekly_by_month") or {}
            explanation["hours_note"] = record.get("hours_note") or ""
            if hours > 0:
                explanation["hours_source"] = (
                    "Hours Worked filled from client weekly rows (template started at 0)"
                )

            validation = self._hours_validation(hours)
            record["validation_status"] = validation["status"]
            explanation["validation"] = validation

            tid = record.get("template_candidate_id")
            if tid is not None and len(template_claims.get(tid, [])) > 1:
                # Identity ambiguity across multiple messy names claiming one template
                explanation.setdefault("identity_flags", []).append(
                    "multiple_client_rows_claim_same_template"
                )
                if record["match_status"] == "matched":
                    record["match_status"] = "potential_duplicate"
                    explanation["identity_summary"] = (
                        f"Multiple client-side names map to the same reference candidate "
                        f"({record.get('template_candidate_name')}). Confirm they are one person."
                    )
                    explanation["audit"] = self._audit_block(
                        headline=f"Duplicate claim: {record.get('template_candidate_name')}",
                        why=explanation["identity_summary"],
                        identity_status="potential_duplicate",
                        validation=validation,
                    )

            # Client conflict only when identity name is strong but clients clearly disagree
            signals = explanation.get("signals") or {}
            if (
                record.get("template_candidate_id") is not None
                and signals.get("identity_compatible")
                and signals.get("client_available")
                and float(signals.get("name_score") or 0) >= 90
                and float(signals.get("client_score") or 0) <= 40
            ):
                explanation.setdefault("identity_flags", []).append("client_mismatch_with_strong_name")
                if record["match_status"] in ("matched", "needs_review"):
                    record["match_status"] = "conflicting"
                    explanation["identity_summary"] = (
                        f"Name strongly resembles reference "
                        f"'{record.get('template_candidate_name')}', but client "
                        f"'{record.get('messy_client_name') or '-'}' does not align with "
                        f"'{signals.get('template_client') or '-'}'. Possible different person."
                    )
                    explanation["audit"] = self._audit_block(
                        headline=f"Conflict: {record.get('template_candidate_name')}",
                        why=explanation["identity_summary"],
                        identity_status="conflicting",
                        validation=validation,
                    )

            # Ensure every record has a per-row audit block
            if "audit" not in explanation:
                explanation["audit"] = self._audit_block(
                    headline=explanation.get("identity_headline") or record.get("match_status"),
                    why=explanation.get("identity_summary") or "",
                    identity_status=record.get("match_status"),
                    validation=validation,
                    alternatives=explanation.get("alternatives") or [],
                )

            results[record["match_status"]].append(record)

        return results

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
            # Dynamic soft boost when one normalized client string contains the other
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

        # Identity-first confidence: name dominates; client/month only refine when identity holds
        if not identity_ok:
            confidence = min(name_score * 0.55, self.REVIEW_THRESHOLD - 1.0)
        else:
            weights = {"name": 0.75, "client": 0.0, "month": 0.0}
            if client_available:
                weights["client"] = 0.18
            if month_available:
                weights["month"] = 0.07
            # Renormalize
            total_w = sum(weights.values()) or 1.0
            for k in weights:
                weights[k] /= total_w
            confidence = (
                name_score * weights["name"]
                + client_score * weights["client"]
                + month_score * weights["month"]
            )
            # Keep confidence close to name evidence
            confidence = max(confidence, name_score * 0.9)

        id_match = False
        messy_id = str(group.get("candidate_id") or "").strip().upper()
        if messy_id and template.get("_candidate_id") and messy_id == template["_candidate_id"]:
            id_match = True
            confidence = min(100.0, confidence + 8.0)
            identity_ok = True

        return {
            "candidate": template,
            "confidence": round(float(confidence), 2),
            "method": name_info["method"] + ("+id" if id_match else ""),
            "identity_compatible": identity_ok,
            "why_suggested": name_info["why"],
            "signals": {
                "name_score": round(name_score, 2),
                "client_score": round(client_score, 2),
                "month_score": round(month_score, 2),
                "identity_compatible": identity_ok,
                "identity_evidence": name_info["evidence"],
                "client_available": client_available,
                "month_available": month_available,
                "id_match": id_match,
                "messy_month": messy_month,
                "template_month": template_month,
                "messy_client": group.get("client_name"),
                "template_client": template.get("client_name"),
            },
        }

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
            }

        if n1 == n2:
            evidence.append("exact_normalized_name")
            return {
                "score": 100.0,
                "compatible": True,
                "method": "exact",
                "why": "Normalized full name matches exactly",
                "evidence": evidence,
            }

        # Token-order insensitive equality (handles First Last vs Last First after normalize)
        if sorted(p1["tokens"]) == sorted(p2["tokens"]) and p1["tokens"]:
            evidence.append("same_tokens_any_order")
            return {
                "score": 99.0,
                "compatible": True,
                "method": "token_permutation",
                "why": "Same name tokens in different order",
                "evidence": evidence,
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

        identity_blend = (
            last_score * 0.40
            + first_score * 0.30
            + token_set * 0.15
            + token_sort * 0.10
            + raw * 0.05
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
        """Only identity-compatible, near-top name variants — never unrelated people."""
        if not best:
            return []
        top_name = float(best["signals"].get("name_score") or 0)
        floor = max(self.MIN_IDENTITY_NAME_SCORE, top_name * self.ALT_RELATIVE_FLOOR)
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
            alts.append({
                "candidate_id": cand.get("candidate_id"),
                "candidate_name": cand.get("candidate_name"),
                "client_name": cand.get("client_name"),
                "confidence": r["confidence"],
                "name_score": name_score,
                "method": r["method"],
                "why_suggested": r.get("why_suggested") or "",
                "signals": {
                    "name_score": name_score,
                    "client_score": r["signals"].get("client_score"),
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
    ) -> Dict[str, Any]:
        return {
            "what_happened": headline,
            "why": why,
            "identity_status": identity_status,
            "validation_status": (validation or {}).get("status"),
            "validation_summary": (validation or {}).get("summary"),
            "has_alternatives": bool(alternatives),
        }

    def _build_match_record(
        self,
        group: Dict[str, Any],
        ranked: List[Dict[str, Any]],
        assigned_template_ids: set,
        target_month: str,
    ) -> Dict[str, Any]:
        # Prefer unassigned, identity-compatible candidates
        available = [
            r for r in ranked
            if r["candidate"]["id"] not in assigned_template_ids and r.get("identity_compatible")
        ]
        # Fallback: any unassigned ranked row (still may be unmatched if weak)
        if not available:
            available = [r for r in ranked if r["candidate"]["id"] not in assigned_template_ids]

        best = available[0] if available else None
        # Ambiguity only among other identity-compatible competitors
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

        # Unmatched: no identity-compatible candidate above review threshold
        if (
            not best
            or not best.get("identity_compatible")
            or best["confidence"] < self.REVIEW_THRESHOLD
            or float(best["signals"].get("name_score") or 0) < self.MIN_IDENTITY_NAME_SCORE
        ):
            alts = self._plausible_alternatives(
                [r for r in ranked if r.get("identity_compatible")],
                best if best and best.get("identity_compatible") else (
                    next((r for r in ranked if r.get("identity_compatible")), None)
                ),
            )
            summary = (
                "No sufficiently similar reference candidate was found in the Hours Template."
            )
            if alts:
                summary = (
                    "No single confident identity match; only weak/partial name variants exist. "
                    "Manual mapping required."
                )
            explanation = {
                "identity_summary": summary,
                "identity_headline": "Unmatched",
                "signals": best["signals"] if best else {},
                "alternatives": alts,
                "identity_flags": [],
                "validation": validation,
                "audit": self._audit_block(
                    headline="Unmatched",
                    why=summary,
                    identity_status="unmatched",
                    validation=validation,
                    alternatives=alts,
                ),
            }
            return {
                **base_fields,
                "template_candidate": None,
                "template_candidate_id": None,
                "template_candidate_name": None,
                "template_candidate_id_str": None,
                "confidence_score": best["confidence"] if best and best.get("identity_compatible") else 0.0,
                "match_method": best["method"] if best and best.get("identity_compatible") else "none",
                "match_status": "unmatched",
                "match_explanation": explanation,
                "alternatives": alts,
            }

        ambiguous = bool(
            second
            and second.get("identity_compatible")
            and (best["confidence"] - second["confidence"]) < self.AMBIGUITY_GAP
            and float(second["signals"].get("name_score") or 0) >= self.MIN_IDENTITY_NAME_SCORE
        )

        cand = best["candidate"]
        alts = self._plausible_alternatives(compatible_pool, best, exclude_id=cand.get("id"))

        if ambiguous:
            status = "needs_review"
            other = second["candidate"].get("candidate_name")
            summary = (
                f"Two reference candidates are highly similar to '{group.get('candidate_name')}': "
                f"'{cand.get('candidate_name')}' ({best['confidence']}%) and "
                f"'{other}' ({second['confidence']}%). Confirm which person is correct."
            )
            headline = f"Needs review: ambiguous between {cand.get('candidate_name')} and {other}"
            flags = ["ambiguous_top_candidates"]
        elif best["confidence"] >= self.AUTO_MATCH_THRESHOLD:
            status = "matched"
            summary = (
                f"Matched to '{cand.get('candidate_name')}' because {best.get('why_suggested')}"
            )
            headline = f"Matched: {cand.get('candidate_name')}"
            flags = []
        else:
            status = "needs_review"
            summary = (
                f"Possible match to '{cand.get('candidate_name')}' "
                f"({best['confidence']}% identity confidence). "
                f"{best.get('why_suggested')}. Confirm before accepting."
            )
            headline = f"Needs review: {cand.get('candidate_name')}"
            flags = ["medium_identity_confidence"]

        explanation = {
            "identity_summary": summary,
            "identity_headline": headline,
            "signals": best["signals"],
            "alternatives": alts,
            "identity_flags": flags,
            "chosen": {
                "candidate_id": cand.get("candidate_id"),
                "candidate_name": cand.get("candidate_name"),
                "client_name": cand.get("client_name"),
                "confidence": best["confidence"],
                "method": best["method"],
                "why": best.get("why_suggested"),
            },
            "validation": validation,
            "audit": self._audit_block(
                headline=headline,
                why=summary,
                identity_status=status,
                validation=validation,
                alternatives=alts,
            ),
        }

        return {
            **base_fields,
            "template_candidate": cand,
            "template_candidate_id": cand.get("id"),
            "template_candidate_name": cand.get("candidate_name"),
            "template_candidate_id_str": cand.get("candidate_id"),
            "confidence_score": best["confidence"],
            "match_method": best["method"],
            "match_status": status,
            "match_explanation": explanation,
            "alternatives": alts,
        }
