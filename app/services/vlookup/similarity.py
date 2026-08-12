from rapidfuzz import fuzz
from metaphone import doublemetaphone
from typing import Optional, Dict
from app.services.vlookup.normalization import normalize_name, normalize_client_name


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
        
        if c1 == c2:
            return 100.0
        
        # Use token-based matching for company names
        score = fuzz.token_sort_ratio(c1, c2)
        
        return float(score)
    
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
