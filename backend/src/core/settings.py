from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # Supabase
    database_url: str
    db_pool_timeout_seconds: int = Field(default=10, ge=1, le=60)
    db_connect_timeout_seconds: int = Field(default=10, ge=1, le=60)
    db_command_timeout_seconds: int = Field(default=20, ge=1, le=120)
    # Upstash Redis
    redis_url: str
    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536
    # GitHub App
    github_app_id: int = 0
    github_app_slug: str = ""
    github_app_client_id: str = ""
    github_app_client_secret: str = ""
    github_app_webhook_secret: str = ""
    github_oauth_callback_url: str = "http://localhost:8000/api/auth/github/callback"
    api_base_url: str = "http://localhost:8000"
    durable_reviews_enabled: bool = True
    branch_reviews_enabled: bool = False
    review_max_files: int = Field(default=50, ge=1, le=500)
    review_max_characters: int = Field(default=100000, ge=1000, le=5000000)
    review_chunk_characters: int = Field(default=12000, ge=1000, le=100000)
    review_job_timeout_seconds: int = Field(default=900, ge=5, le=86400)
    worker_lease_seconds: int = Field(default=90, ge=10, le=3600)
    allowed_origins: str = "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174"
    github_app_private_key_path: str = "github_app_private_key.pem"
    frontend_base_url: str = "http://localhost:5173"
    # Legacy GitHub PAT kept temporarily during the review execution refactor
    github_pat: str = ""
    # Clerk
    clerk_secret_key: str
    clerk_webhook_secret: str = ""
    # Encryption
    encryption_key: str
    # LangSmith
    langsmith_api_key: str = ""
    langsmith_tracing: bool = False
    langsmith_project: str = "devreason"
    # NVD
    nvd_api_key: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",    # silently ignore any env vars not defined above
    )

settings = Settings()
