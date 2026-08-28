"""Identity types shared by the auth service and the dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # avoids a types -> models import at runtime
    from api.models import ApiKey, Organization


@dataclass
class SupabaseIdentity:
    """The parts of a verified Supabase token this app uses."""

    user_id: str
    email: str
    display_name: Optional[str]
    avatar_url: Optional[str]


class AuthError(Exception):
    """Sign-in failed. The message is safe to show a user."""


class ApiCaller:
    """A server authenticated with an API key."""

    def __init__(self, key: "ApiKey", organization: "Organization"):
        self.key = key
        self.organization = organization

    @property
    def mode(self) -> str:
        return self.key.mode

    @property
    def is_test(self) -> bool:
        return self.key.mode == "test"
