"""Auth repository — SQL only."""

from typing import List, Optional, Sequence

from sqlalchemy.orm import Session, joinedload

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
