from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler
from metaphone import doublemetaphone
from typing import Any, Dict, Optional

from app.services.vlookup.normalization import normalize_name, normalize_client_name, parse_name_tokens


class SimilarityScorer:
    
    @staticmethod
    def name_similarity(name1: Optional[str], name2: Optional[str]) -> float:
        if not name1 or not name2:
            return 0.0
        
        n1 = normalize_name(name1)
        n2 = normalize_name(name2)
        
        if n1 == n2:
            return 100.0
        
        # Levenshtein ratio (0-100 scale)
        levenshtein_score = fuzz.ratio(n1, n2)
        
        # Token-based similarity
        token_score = fuzz.token_sort_ratio(n1, n2)
        token_set_score = fuzz.token_set_ratio(n1, n2)
        
        # Phonetic similarity
        phonetic_score = _phonetic_similarity(n1, n2)
        
        # Weighted average
        score = (
            levenshtein_score * 0.35 +
            token_score * 0.30 +
            token_set_score * 0.20 +
            phonetic_score * 0.15
        )
        
        return min(100.0, max(0.0, score))
    
    @staticmethod
    def client_similarity(client1: Optional[str], client2: Optional[str]) -> float:
        if not client1 or not client2:
            return 0.0

        c1 = normalize_client_name(client1)
        c2 = normalize_client_name(client2)

        if not c1 or not c2:
            return 0.0

        if c1 == c2:
            return 100.0

        # One normalized label contained in the other (e.g. Abbott vs Abbott 4215 leftovers)
        if c1 in c2 or c2 in c1:
            shorter, longer = (c1, c2) if len(c1) <= len(c2) else (c2, c1)
            if len(shorter) >= 3 and longer.startswith(shorter):
                return 95.0
            return max(88.0, float(fuzz.token_set_ratio(c1, c2)))

        # Token-based matching for company names
        score = float(fuzz.token_sort_ratio(c1, c2))
        set_score = float(fuzz.token_set_ratio(c1, c2))
        return max(score, set_score)
    
    @staticmethod
    def exact_match(value1: Optional[str], value2: Optional[str], normalize_func=None) -> bool:
        """Check if two values match exactly after normalization"""
        if not value1 or not value2:
            return False
        
        if normalize_func:
            v1 = normalize_func(value1)
            v2 = normalize_func(value2)
        else:
            v1 = normalize_name(value1)
            v2 = normalize_name(value2)
        
        return v1 == v2
    
    @staticmethod
    def date_similarity(date1_str: Optional[str], date2_str: Optional[str]) -> float:
        """
        Compare dates (month/year level).
        Returns 100 if same month/year, 80 if off by 1 month, 0 if different.
        """
        if not date1_str or not date2_str:
            return 0.0
        
        try:
            from datetime import datetime
            
            # Parse dates
            if isinstance(date1_str, str):
                # Try parsing M/YYYY format
                if '/' in date1_str:
                    parts = date1_str.split('/')
                    m1, y1 = int(parts[0]), int(parts[1])
                else:
                    # Assume datetime object
                    d1 = datetime.fromisoformat(str(date1_str))
                    m1, y1 = d1.month, d1.year
            else:
                m1, y1 = date1_str.month, date1_str.year
            
            if isinstance(date2_str, str):
                if '/' in date2_str:
                    parts = date2_str.split('/')
                    m2, y2 = int(parts[0]), int(parts[1])
                else:
                    d2 = datetime.fromisoformat(str(date2_str))
                    m2, y2 = d2.month, d2.year
            else:
                m2, y2 = date2_str.month, date2_str.year
            
            # Same month/year
            if m1 == m2 and y1 == y2:
                return 100.0
            
            # Off by one month
            if y1 == y2 and abs(m1 - m2) <= 1:
                return 80.0
            
            # Different
            return 0.0
            
        except Exception:
            return 0.0


def _phonetic_similarity(name1: str, name2: str) -> float:
    """
    Calculate phonetic similarity using Metaphone.
    Returns 0 or 100.
    """
    try:
        meta1 = doublemetaphone(name1)
        meta2 = doublemetaphone(name2)
        
        # Check if any metaphone encoding matches
        if meta1[0] == meta2[0] and meta1[0]:  # Primary encoding
            return 100.0
        if meta1[1] == meta2[1] and meta1[1]:  # Secondary encoding
            return 100.0
        
        return 0.0
    except Exception:
        return 0.0


def calculate_weighted_score(
    scores: Dict[str, float],
    weights: Dict[str, float]
) -> float:
    """
    Calculate weighted average of multiple scores.
    
    Args:
        scores: Dict of score_name -> score_value (0-100)
        weights: Dict of score_name -> weight (sum should be ~1.0)
    
    Returns:
        Weighted score (0-100)
    """
    total_score = 0.0
    total_weight = 0.0
    
    for key, score in scores.items():
        weight = weights.get(key, 0.0)
        total_score += score * weight
        total_weight += weight
    
    if total_weight == 0:
        return 0.0
    
    return min(100.0, max(0.0, total_score / total_weight))


def _pct(value: float) -> float:
    v = float(value or 0)
    return v * 100.0 if 0.0 <= v <= 1.0 else v


def _char_ngram_score(a: str, b: str, n: int = 3) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 100.0
    compact_a = a.replace(" ", "")
    compact_b = b.replace(" ", "")
    if compact_a == compact_b:
        return 100.0

    def grams(text: str) -> set:
        if len(text) < n:
            return {text} if text else set()
        return {text[i : i + n] for i in range(len(text) - n + 1)}

    g1, g2 = grams(compact_a), grams(compact_b)
    if not g1 or not g2:
        return 0.0
    return 100.0 * len(g1 & g2) / len(g1 | g2)


def name_feature_scores(
    name1: Optional[str],
    name2: Optional[str],
    parts1: Optional[Dict[str, Any]] = None,
    parts2: Optional[Dict[str, Any]] = None,
) -> Dict[str, float]:
    """
    Multi-algorithm name features (0-100). Used for scoring and explainability.

    Does not decide identity by itself — identity gates stay in ReconciliationMatcher.
    """
    p1 = parts1 or parse_name_tokens(name1)
    p2 = parts2 or parse_name_tokens(name2)
    n1 = str(p1.get("normalized") or "")
    n2 = str(p2.get("normalized") or "")
    compact1 = str(p1.get("compact") or "".join(p1.get("tokens") or []))
    compact2 = str(p2.get("compact") or "".join(p2.get("tokens") or []))
    first1, first2 = str(p1.get("first") or ""), str(p2.get("first") or "")
    last1, last2 = str(p1.get("last") or ""), str(p2.get("last") or "")
    init1, init2 = str(p1.get("initials_str") or ""), str(p2.get("initials_str") or "")

    empty = {
        "name_exact": 0.0,
        "name_token_similarity": 0.0,
        "name_token_sort_similarity": 0.0,
        "name_token_set_similarity": 0.0,
        "name_jaro_similarity": 0.0,
        "name_edit_similarity": 0.0,
        "name_ngram_similarity": 0.0,
        "first_name_similarity": 0.0,
        "last_name_similarity": 0.0,
        "initial_similarity": 0.0,
        "compact_match": 0.0,
    }
    if not n1 or not n2:
        return empty

    exact = 100.0 if n1 == n2 else 0.0
    compact = 100.0 if compact1 and compact1 == compact2 else 0.0
    token_sort = float(fuzz.token_sort_ratio(n1, n2))
    token_set = float(fuzz.token_set_ratio(n1, n2))
    token_ratio = float(fuzz.token_ratio(n1, n2)) if hasattr(fuzz, "token_ratio") else token_set
    jaro = _pct(JaroWinkler.similarity(n1, n2))
    edit = float(fuzz.ratio(n1, n2))
    ngram = max(_char_ngram_score(n1, n2), float(fuzz.QRatio(n1, n2)) if hasattr(fuzz, "QRatio") else 0.0)
    first = float(fuzz.ratio(first1, first2)) if first1 and first2 else 0.0
    last = float(fuzz.ratio(last1, last2)) if last1 and last2 else 0.0
    initials = 100.0 if init1 and init1 == init2 else (
        float(fuzz.ratio(init1, init2)) if init1 and init2 else 0.0
    )

    return {
        "name_exact": exact,
        "name_token_similarity": token_ratio,
        "name_token_sort_similarity": token_sort,
        "name_token_set_similarity": token_set,
        "name_jaro_similarity": round(jaro, 2),
        "name_edit_similarity": edit,
        "name_ngram_similarity": round(ngram, 2),
        "first_name_similarity": first,
        "last_name_similarity": last,
        "initial_similarity": initials,
        "compact_match": compact,
    }
