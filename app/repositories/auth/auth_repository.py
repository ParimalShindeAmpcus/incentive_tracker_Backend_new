"""Auth repository — SQL only."""

from datetime import datetime
from typing import List, Optional, Sequence

from sqlalchemy.orm import Session, joinedload

from app.repositories.entities.auth_revocation import RevokedToken
from app.repositories.entities.user import Role, User


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return (
        db.query(User)
        .options(joinedload(User.roles))
        .filter(User.email == email)
        .first()
    )


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return (
        db.query(User)
        .options(joinedload(User.roles))
        .filter(User.id == user_id)
        .first()
    )


def list_roles(db: Session) -> List[Role]:
    return db.query(Role).order_by(Role.name).all()


def get_role_by_name(db: Session, name: str) -> Optional[Role]:
    return db.query(Role).filter(Role.name == name).first()


def create_role(db: Session, name: str, description: Optional[str] = None) -> Role:
    role = Role(name=name, description=description)
    db.add(role)
    db.flush()
    return role


def create_user(
    db: Session,
    *,
    email: str,
    full_name: str,
    hashed_password: str,
    roles: Optional[Sequence[Role]] = None,
    is_active: bool = True,
) -> User:
    user = User(
        email=email,
        full_name=full_name,
        hashed_password=hashed_password,
        is_active=is_active,
    )
    if roles:
        user.roles = list(roles)
    db.add(user)
    db.flush()
    return user


def revoke_token(
    db: Session,
    jti: str,
    token_type: str,
    expires_at: datetime,
    user_id: Optional[int] = None,
) -> None:
    # Use an upsert-like logic or check if already revoked to avoid unique constraint errors
    existing = db.query(RevokedToken).filter(RevokedToken.jti == jti).first()
    if not existing:
        revoked = RevokedToken(
            jti=jti,
            user_id=user_id,
            token_type=token_type,
            expires_at=expires_at,
        )
        db.add(revoked)
        db.commit()


def is_token_revoked(db: Session, jti: str) -> bool:
    return db.query(RevokedToken).filter(RevokedToken.jti == jti).first() is not None


def cleanup_expired_tokens(db: Session) -> None:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    db.query(RevokedToken).filter(RevokedToken.expires_at < now).delete(synchronize_session=False)
    db.commit()
