"""
Every table in one namespace.

Importing this module is what registers the tables on ``Base.metadata``, so
anything that creates or inspects the schema imports it rather than the
individual modules.
"""

from api.database.base import Base
from api.models.api_key import ApiKey
from api.models.dataset import DatasetRecord
from api.models.job import Job
from api.models.model import ModelRecord
from api.models.organization import Membership, Organization
from api.models.usage import UsageEvent
from api.models.user import Session, User

__all__ = [
    "ApiKey",
    "Base",
    "DatasetRecord",
    "Job",
    "Membership",
    "ModelRecord",
    "Organization",
    "Session",
    "UsageEvent",
    "User",
]
