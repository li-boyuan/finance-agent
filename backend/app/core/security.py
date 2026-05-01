from cryptography.fernet import Fernet
from jose import JWTError, jwt

from app.config import settings

fernet = Fernet(settings.token_encryption_key.encode())


def encrypt_token(token: str) -> bytes:
    return fernet.encrypt(token.encode())


def decrypt_token(encrypted: bytes) -> str:
    return fernet.decrypt(encrypted).decode()


def verify_supabase_jwt(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except JWTError:
        return None
