import os
from typing import Optional

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from . import models


pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_current_user(session: dict, db: Session) -> Optional[models.User]:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.query(models.User).filter(models.User.id == user_id).first()


def app_secret() -> str:
    return os.getenv("APP_SECRET", "dev-secret-change-me")
