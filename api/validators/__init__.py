"""
Request and response shapes.

These are the contract the typed frontend client is generated against, so the
field names here are the field names in the dashboard. Pydantic does the
validating, which is why they live together rather than beside the handlers.
"""

from api.validators.auth import MeResponse, SessionRequest
from api.validators.common import MAX_ID_LEN
from api.validators.dataset import ColumnMapping, DatasetOut, ScoreDatasetRequest
from api.validators.job import JobOut
from api.validators.organization import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    OrganizationCreate,
    OrganizationOut,
)
from api.validators.risk import (
    GraphLink,
    ProcessingStage,
    Reason,
    ScoreResponse,
    TransactionRequest,
)
from api.validators.training import TrainingRequest
from api.validators.webhook import WebhookEndpointCreate

__all__ = [
    "MAX_ID_LEN",
    "ApiKeyCreate",
    "ApiKeyCreated",
    "ApiKeyOut",
    "ColumnMapping",
    "DatasetOut",
    "GraphLink",
    "JobOut",
    "MeResponse",
    "OrganizationCreate",
    "OrganizationOut",
    "ProcessingStage",
    "Reason",
    "ScoreDatasetRequest",
    "ScoreResponse",
    "SessionRequest",
    "TrainingRequest",
    "TransactionRequest",
    "WebhookEndpointCreate",
]
