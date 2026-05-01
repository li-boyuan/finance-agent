from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    jwt_secret: str
    token_encryption_key: str
    ibkr_client_id: str = ""
    ibkr_client_secret: str = ""
    ibkr_redirect_uri: str = "http://localhost:3000/api/ibkr/callback"
    redis_url: str = "redis://localhost:6379"
    cors_origins: str = "http://localhost:3000"

    model_config = {"env_file": ".env"}


settings = Settings()
