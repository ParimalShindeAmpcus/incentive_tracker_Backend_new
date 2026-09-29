"""Formula injection protection and Excel/CSV cell sanitization."""

from typing import Any

DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_excel_cell(value: Any) -> Any:
    """Neutralize spreadsheet formula injection by prepending a single quote to dangerous prefixes.
    
    Prevents formulas like =HYPERLINK(), =cmd|..., @SUM, +1+1, -5 from executing when opened
    in spreadsheet software like Excel, Calc, Google Sheets.
    """
    if isinstance(value, str):
        if value.startswith(DANGEROUS_PREFIXES) or value.lstrip().startswith(DANGEROUS_PREFIXES):
            return f"'{value}"
    return value
