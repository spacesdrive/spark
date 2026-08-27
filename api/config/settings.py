"""
Every setting the API reads, in one place.

All of it comes from the environment. Nothing here has a real credential as a
default, and the secret files in the project root are never read by this code:
you copy the values you need into a ``.env`` file. See ``.env.example``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

def _project_root() -> Path:
    """
    The directory holding the project, found by looking for its marker.

    Counting parent directories would silently point at the wrong place the
    next time this file moves, and the value here decides where the database,
    the uploads and the model artifacts live.
    """
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return here.parents[2]


ROOT = _project_root()


class Settings(BaseSettings):
    """Configuration for the Spark API."""

    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # environment
    environment: str = "development"
    debug: bool = False

    # where things live
    database_url: str = f"sqlite:///{(ROOT / 'data' / 'spark.db').as_posix()}"
    artifact_dir: str = str(ROOT / "artifacts")
    upload_dir: str = str(ROOT / "data" / "uploads")
    user_model_dir: str = str(ROOT / "data" / "user_models")

    # public addresses
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"
    public_domain: str = "spark.spacesdrive.cc"
    #: One level of subdomain, because Cloudflare Universal SSL does not cover
    #: a two level name and "docs.spark..." fails TLS before it reaches us.
    docs_domain: str = "docs-spark.spacesdrive.cc"
    github_repo: str = "spacesdrive/spark"

    #: Browser origins allowed to call the API with credentials.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # cache
    #: Upstash Redis over its REST API. Optional: with these unset, Spark runs
    #: exactly as before and simply recomputes what it would have cached.
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""
    #: How long a cached evaluation report stays valid. These reports only
    #: change when a new model is deployed, and the cache key already includes
    #: the model version, so this is a safety net rather than the mechanism.
    cache_ttl_seconds: int = 900

    # authentication
    #: Supabase project URL, for example https://abcdefgh.supabase.co
    supabase_url: str = ""
    #: Anonymous key. Public by design, safe in the browser bundle.
    supabase_anon_key: str = ""
    #: Only set on legacy projects that still sign tokens with HS256.
    supabase_jwt_secret: str = ""
    #: Signs the session cookie. Generate with: python -c "import secrets;
    #: print(secrets.token_urlsafe(48))"
    session_secret: str = ""
    session_cookie_name: str = "spark_session"
    csrf_cookie_name: str = "spark_csrf"
    session_ttl_hours: int = 24 * 7
    #: Cookies are marked Secure unless this is a local development run.
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    #: Set when the API and the dashboard sit on different subdomains of one
    #: registrable domain, for example ".spacesdrive.cc". Leave empty for
    #: same-origin deployments.
    cookie_domain: str = ""

    # upload and evaluation limits
    max_upload_bytes: int = 25 * 1024 * 1024
    max_test_rows: int = 100_000
    max_training_rows: int = 200_000
    min_training_rows: int = 2_000
    max_files_per_upload: int = 1
    max_model_bytes: int = 100 * 1024 * 1024
    max_training_seconds: int = 900
    max_concurrent_jobs: int = 2
    max_jobs_per_org_per_day: int = 20
    dataset_retention_hours: int = 24

    # rate limits, requests per minute
    rate_limit_public: int = 60
    rate_limit_authenticated: int = 240
    rate_limit_scoring: int = 120
    rate_limit_upload: int = 10

    # model loading
    #: Load the scoring engine when the process starts. Turning it off makes
    #: the API boot instantly and load on the first scoring request instead,
    #: which is what the tests use.
    eager_model_load: bool = True

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod")

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def supabase_jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def supabase_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def auth_configured(self) -> bool:
        """True when sign-in can actually work."""
        return bool(self.supabase_url and self.session_secret)

    def limits_public(self) -> dict:
        """The limits shown to users, so the numbers on screen are the real ones."""
        return {
            "max_upload_bytes": self.max_upload_bytes,
            "max_test_rows": self.max_test_rows,
            "max_training_rows": self.max_training_rows,
            "min_training_rows": self.min_training_rows,
            "max_files_per_upload": self.max_files_per_upload,
            "max_training_seconds": self.max_training_seconds,
            "max_concurrent_jobs": self.max_concurrent_jobs,
            "max_jobs_per_org_per_day": self.max_jobs_per_org_per_day,
            "dataset_retention_hours": self.dataset_retention_hours,
            "accepted_formats": ["csv"],
        }


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    for d in (s.upload_dir, s.user_model_dir):
        Path(d).mkdir(parents=True, exist_ok=True)

    # Only SQLite keeps its database in a file that needs a directory. Running
    # this for any other URL treats the connection string as a path and tries
    # to create a directory called "postgresql+psycopg:".
    if s.database_url.startswith("sqlite"):
        Path(s.database_url.replace("sqlite:///", "")).parent.mkdir(
            parents=True, exist_ok=True
        )
    return s


settings = get_settings()
