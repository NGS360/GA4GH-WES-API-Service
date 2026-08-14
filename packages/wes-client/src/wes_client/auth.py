"""
Authentication strategies for the WES client.

WES accepts three kinds of credential (see wes_service.core.security), and this
module offers one class per kind so a caller picks a credential rather than
assembling headers. They are httpx.Auth subclasses, so the credential attaches
to every request the client makes without any operation needing to know it
exists.

Deliberately absent here: the asserted identity, X-On-Behalf-Of. That is not a
credential -- it is a claim a service makes on a per-request basis about who it
is acting for -- so it lives on the client (see WesClient.on_behalf_of) rather
than being baked into an auth object. Keeping the two apart is what lets one
pooled client serve requests for many different users.
"""

from __future__ import annotations

from collections.abc import Generator

import httpx

# Re-exported so callers need only one import for the common case.
BasicAuth = httpx.BasicAuth


class ServiceKeyAuth(httpx.Auth):
    """
    Shared-secret authentication for a trusted sibling service.

    This is the credential NGS360 APIServer uses. WES accepts it without any
    outbound validation call, which is the point: APIServer fronts WES for the
    browser, so a credential WES had to phone APIServer to check would make
    APIServer wait on itself.

    A holder of this key is trusted to assert an identity via
    WesClient.on_behalf_of. That assertion is for WES's audit trail and is NOT
    an authorization input -- authorization for service-fronted requests stays
    with the calling service.
    """

    def __init__(self, key: str) -> None:
        if not key:
            # An empty key would send an empty header, and a server whose own
            # key was unset could then authenticate it. Refusing at construction
            # turns that into a startup failure instead of a silent hole.
            raise ValueError("service key must not be empty")
        self._key = key

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["X-Internal-Service-Key"] = self._key
        yield request


class BearerAuth(httpx.Auth):
    """
    NGS360 API token authentication, for a client acting as a real user.

    WES validates these by calling NGS360's /auth/me. Correct for CLI users and
    standalone scripts; wrong for NGS360 APIServer itself, which would be
    calling back into itself -- use ServiceKeyAuth there.
    """

    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError("bearer token must not be empty")
        self._token = token

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request


__all__ = ["BasicAuth", "BearerAuth", "ServiceKeyAuth"]
