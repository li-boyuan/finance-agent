import logging

import httpx
from cryptography.fernet import Fernet
from jose import JWTError, jwt, jwk

from app.config import settings

logger = logging.getLogger("security")
fernet = Fernet(settings.token_encryption_key.encode())

_jwks_cache: dict | None = None


def encrypt_token(token: str) -> bytes:
    return fernet.encrypt(token.encode())


def decrypt_token(encrypted: bytes) -> str:
    return fernet.decrypt(encrypted).decode()


def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache
    jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    try:
        resp = httpx.get(jwks_url, timeout=5)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        logger.info("JWKS loaded: %d keys", len(_jwks_cache.get("keys", [])))
    except Exception as e:
        logger.warning("Failed to fetch JWKS: %s", e)
        _jwks_cache = {"keys": []}
    return _jwks_cache


def verify_supabase_jwt(token: str) -> dict:
    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg", "HS256")

        if alg == "ES256":
            kid = header.get("kid")
            jwks = _get_jwks()
            key = None
            for key_data in jwks.get("keys", []):
                if key_data.get("kid") == kid:
                    key = jwk.construct(key_data, algorithm="ES256")
                    break
            if key is None:
                logger.error("No matching JWKS key found for kid=%s", kid)
                return None
            payload = jwt.decode(
                token, key, algorithms=["ES256"], audience="authenticated",
            )
        else:
            payload = jwt.decode(
                token, settings.jwt_secret,
                algorithms=["HS256"], audience="authenticated",
            )
        return payload
    except JWTError as e:
        logger.error("JWT verification failed: %s", e)
        return None
