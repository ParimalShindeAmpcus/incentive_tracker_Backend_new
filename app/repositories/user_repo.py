from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.models.user import Role, User


def get_by_email(db: Session, email: str) -> Optional[User]:
    return (
        db.query(User)
        .options(joinedload(User.roles))
        .filter(User.email == email.lower())
        .first()
    )


def get_by_id(db: Session, user_id: int) -> Optional[User]:
    return (
        db.query(User)
        .options(joinedload(User.roles))
        .filter(User.id == user_id)
        .first()
    )


def get_role_by_name(db: Session, name: str) -> Optional[Role]:
    return db.query(Role).filter(Role.name == name.upper()).first()


def list_users(db: Session, *, offset: int = 0, limit: int = 50) -> List[User]:
    return (
        db.query(User)
        .options(joinedload(User.roles))
        .offset(offset)
        .limit(limit)
        .all()
    )
