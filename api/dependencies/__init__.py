"""
FastAPI dependencies.

Split by what they answer: how often may you call, who are you, and may you
touch this particular row.
"""

from api.dependencies.auth import (
    api_key_caller,
    current_user,
    current_user_optional,
    require_api_key,
    require_csrf,
)
from api.dependencies.rate_limit import (
    client_key,
    rate_limit_public,
    rate_limit_scoring,
    rate_limit_upload,
)
from api.dependencies.resources import (
    dataset_or_404,
    job_or_404,
    membership_or_403,
    model_or_404,
    org_or_404,
)

__all__ = [
    "api_key_caller",
    "client_key",
    "current_user",
    "current_user_optional",
    "dataset_or_404",
    "job_or_404",
    "membership_or_403",
    "model_or_404",
    "org_or_404",
    "rate_limit_public",
    "rate_limit_scoring",
    "rate_limit_upload",
    "require_api_key",
    "require_csrf",
]
