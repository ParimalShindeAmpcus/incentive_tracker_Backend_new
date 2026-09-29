from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from mis.core.config import settings

JWT_SECRET = settings.JWT_SECRET_KEY
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

ROLE_CODE_TO_UI = {
    "RECRUITER": "Recruiter",
    "MANAGER": "Manager",
    "MIS": "Admin",
    "TEAM_LEAD": "Team Lead",
    "HOD": "HOD",
    "ONBOARD_TEAM": "Onboard Team",
    "CRM": "CRM",
    "SENIOR_MANAGER": "Senior Manager",
    "ASSOCIATE_DIRECTOR": "Associate Director",
    "DIRECTOR": "Director",
    "CENTER_HEAD": "Center Head",
    "AVP": "AVP",
}

UI_ROLE_TO_CODE = {
    "recruiter": "RECRUITER",
    "manager": "MANAGER",
    "admin": "MIS",
    "team lead": "TEAM_LEAD",
    "team_lead": "TEAM_LEAD",
    "hod": "HOD",
    "onboard": "ONBOARD_TEAM",
    "onboard team": "ONBOARD_TEAM",
    "onboard_team": "ONBOARD_TEAM",
    "crm": "CRM",
    "senior manager": "SENIOR_MANAGER",
    "senior_manager": "SENIOR_MANAGER",
    "associate director": "ASSOCIATE_DIRECTOR",
    "associate_director": "ASSOCIATE_DIRECTOR",
    "director": "DIRECTOR",
    "center head": "CENTER_HEAD",
    "center_head": "CENTER_HEAD",
    "avp": "AVP",
    "Recruiter": "RECRUITER",
    "Manager": "MANAGER",
    "Admin": "MIS",
    "Team Lead": "TEAM_LEAD",
    "HOD": "HOD",
    "Onboard Team": "ONBOARD_TEAM",
    "CRM": "CRM",
    "Senior Manager": "SENIOR_MANAGER",
    "Associate Director": "ASSOCIATE_DIRECTOR",
    "Director": "DIRECTOR",
    "Center Head": "CENTER_HEAD",
    "AVP": "AVP",
}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.strip().encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str | None) -> bool:
    """Verify bcrypt hashes only."""
    if not hashed:
        return False
    plain = plain.strip()
    stored = hashed.strip()
    if not plain or not stored:
        return False
    if not stored.startswith(("$2a$", "$2b$", "$2y$")):
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), stored.encode("utf-8"))
    except ValueError:
        return False


def is_bcrypt_hash(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().startswith(("$2a$", "$2b$", "$2y$"))


def create_access_token(*, user_id: int, email: str, role_code: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role_code,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def generate_password_reset_token() -> str:
    import secrets

    return secrets.token_urlsafe(32)


def hash_reset_token(token: str) -> str:
    import hashlib

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_reset_token(token: str, token_hash: str) -> bool:
    import hmac

    return hmac.compare_digest(hash_reset_token(token), token_hash)
