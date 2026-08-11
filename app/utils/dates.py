from datetime import date, datetime
from typing import Optional, Union


def parse_date(value: Union[str, date, datetime, None]) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def month_key(value: Union[str, date, datetime, None]) -> Optional[str]:
    if isinstance(value, str) and len(value) == 7 and value[4] == "-":
        return value
    d = parse_date(value)
    if not d:
        return None
    return f"{d.year:04d}-{d.month:02d}"
