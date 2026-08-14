"""
Exceptions raised by the WES client.

These describe what happened to the CALL, not what the caller should return to
whoever asked them. That distinction is the reason this hierarchy exists rather
than the client raising HTTP status codes directly: the same failure means
different things to different consumers. When NGS360 APIServer gets a 404 from
WES while fronting a browser request it is a genuine "no such run"; when a
nightly reconciliation job gets one it is a data-integrity alarm. Only the
caller knows which.

So the client reports the failure faithfully and lets each consumer decide. The
mapping to an outward-facing status code belongs at that consumer's edge.
"""

from __future__ import annotations


class WesError(Exception):
    """Base class for every failure raised by this client."""


class WesTimeout(WesError):
    """The service did not respond within the configured timeout."""


class WesUnavailable(WesError):
    """
    The request never reached the service.

    Connection refused, DNS failure, TLS failure, connection dropped mid-flight.
    Distinguished from WesTimeout because it is usually retryable sooner and
    points at different operational causes.
    """


class WesProtocolError(WesError):
    """
    The service answered, but not with something this client understands.

    An undecodable body, or a body that does not validate against the schema the
    endpoint is declared to return. This is a contract violation between client
    and server -- a deployment skew or a genuine bug -- and never the fault of
    whoever called the client. The contract tests in this repo exist to make it
    fire in CI rather than in production.
    """


class WesResponseError(WesError):
    """
    The service returned a non-2xx status.

    Attributes:
        status_code: The HTTP status the service returned.
        message: The service's error message if it sent a parseable one,
            otherwise a truncated excerpt of the raw body.
        body: The raw response body, truncated. For logs, not for control flow.
    """

    def __init__(self, status_code: int, message: str, body: str = "") -> None:
        super().__init__(f"WES returned {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.body = body


class WesAuthError(WesResponseError):
    """Credentials were missing, rejected, or insufficient (401 or 403)."""


class WesNotFound(WesResponseError):
    """The requested run, task, or resource does not exist (404)."""


class WesBadRequest(WesResponseError):
    """The service rejected the request as malformed (other 4xx)."""


class WesServerError(WesResponseError):
    """The service failed while handling the request (5xx)."""


def response_error(status_code: int, message: str, body: str = "") -> WesResponseError:
    """Build the most specific WesResponseError subclass for a status code."""
    if status_code in (401, 403):
        cls: type[WesResponseError] = WesAuthError
    elif status_code == 404:
        cls = WesNotFound
    elif 400 <= status_code < 500:
        cls = WesBadRequest
    else:
        cls = WesServerError
    return cls(status_code, message, body)
