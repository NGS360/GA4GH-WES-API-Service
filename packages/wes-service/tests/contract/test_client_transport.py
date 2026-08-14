"""
Transport-level tests: failures a healthy server will not produce on demand.

Timeouts, dropped connections, malformed bodies, and credential headers cannot be
provoked from the real app, so these use httpx.MockTransport. The split matters:
everything that CAN be checked against the real server is checked there, and this
file is limited to what genuinely cannot.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from wes_client import (
    AsyncWesClient,
    BasicAuth,
    BearerAuth,
    ServiceKeyAuth,
    WesAuthError,
    WesBadRequest,
    WesNotFound,
    WesProtocolError,
    WesServerError,
    WesTimeout,
    WesUnavailable,
)

# The smallest valid success body of any endpoint. Used by the tests below that
# care about headers or URLs rather than about a particular payload -- picking the
# smallest response keeps them from breaking when a larger model gains a field.
RUN_STATUS = {"run_id": "r", "state": "COMPLETE"}


def client_over(handler: Any, **kwargs: Any) -> AsyncWesClient:
    """Build a client whose transport is the given request handler."""
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://wes.test",
        **kwargs,
    )
    return AsyncWesClient(http_client=http)


def responder(status: int = 200, json_body: Any = None, text: str | None = None) -> Any:
    """A handler returning one fixed response, recording the requests it saw."""

    def handler(request: httpx.Request) -> httpx.Response:
        handler.requests.append(request)  # type: ignore[attr-defined]
        if text is not None:
            return httpx.Response(status, text=text)
        return httpx.Response(status, json=json_body)

    handler.requests = []  # type: ignore[attr-defined]
    return handler


class TestTransportFailures:
    """A request that never completes."""

    async def test_timeout_becomes_wes_timeout(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("too slow", request=request)

        with pytest.raises(WesTimeout) as caught:
            await client_over(handler).get_service_info()

        assert "timed out" in str(caught.value)

    async def test_connect_failure_becomes_wes_unavailable(self) -> None:
        """
        Distinguished from a timeout, because they mean different things.

        A timeout suggests an overloaded service still doing work; a connect
        failure means nothing is listening. Consumers retry them differently.
        """

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        with pytest.raises(WesUnavailable):
            await client_over(handler).get_service_info()


class TestStatusMapping:
    """Non-2xx responses become the matching exception subclass."""

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (400, WesBadRequest),
            (401, WesAuthError),
            (403, WesAuthError),
            (404, WesNotFound),
            (409, WesBadRequest),
            (500, WesServerError),
            (502, WesServerError),
            (503, WesServerError),
        ],
    )
    async def test_status_maps_to_exception(self, status: int, expected: type) -> None:
        with pytest.raises(expected) as caught:
            await client_over(responder(status, {"msg": "nope", "status_code": status})).get_run("r")

        assert caught.value.status_code == status

    async def test_error_response_message_is_extracted(self) -> None:
        """The service's own ErrorResponse `msg` reaches the caller."""
        handler = responder(404, {"msg": "Workflow run not found", "status_code": 404})

        with pytest.raises(WesNotFound) as caught:
            await client_over(handler).get_run("r")

        assert caught.value.message == "Workflow run not found"

    async def test_fastapi_detail_message_is_extracted(self) -> None:
        """
        FastAPI's HTTPException shape is understood too.

        WES raises both shapes -- `msg` from its exception handlers, `detail` from
        HTTPException -- so a client that only knew one would report an empty
        message for half the failures.
        """
        handler = responder(400, {"detail": "Invalid JSON format for filters parameter"})

        with pytest.raises(WesBadRequest) as caught:
            await client_over(handler).get_run("r")

        assert caught.value.message == "Invalid JSON format for filters parameter"

    async def test_non_json_error_body_falls_back_to_text(self) -> None:
        """An HTML error page from a proxy still produces a usable message."""
        handler = responder(502, text="<html><body>Bad Gateway</body></html>")

        with pytest.raises(WesServerError) as caught:
            await client_over(handler).get_run("r")

        assert "Bad Gateway" in caught.value.message

    async def test_error_body_is_truncated(self) -> None:
        """A huge error body cannot flood the caller's logs."""
        handler = responder(500, text="x" * 100_000)

        with pytest.raises(WesServerError) as caught:
            await client_over(handler).get_run("r")

        assert len(caught.value.body) <= 500


class TestProtocolViolations:
    """
    A 2xx the client cannot make sense of.

    These are deployment skew or a bug, never the caller's fault, so they get
    their own exception type rather than being folded in with a 4xx.
    """

    async def test_non_json_success_body(self) -> None:
        with pytest.raises(WesProtocolError) as caught:
            await client_over(responder(200, text="not json at all")).get_service_info()

        assert "non-JSON" in str(caught.value)

    async def test_body_that_does_not_match_the_model(self) -> None:
        with pytest.raises(WesProtocolError) as caught:
            await client_over(responder(200, {"unexpected": "shape"})).get_service_info()

        assert "ServiceInfo" in str(caught.value)

    async def test_unknown_enum_value_is_a_protocol_error(self) -> None:
        """
        A state this client does not know about surfaces here, not downstream.

        Better than passing an unrecognised string through and letting a UI render
        a badge for a state it has no styling for.
        """
        handler = responder(200, {"run_id": "r", "state": "TELEPORTING"})

        with pytest.raises(WesProtocolError):
            await client_over(handler).get_run_status("r")


class TestCredentials:
    """Each auth strategy puts the right thing on the wire."""

    async def test_service_key_header(self) -> None:
        handler = responder(200, RUN_STATUS)
        await client_over(handler, auth=ServiceKeyAuth("secret-key")).get_run_status("r")

        assert handler.requests[0].headers["X-Internal-Service-Key"] == "secret-key"

    async def test_bearer_header(self) -> None:
        handler = responder(200, RUN_STATUS)
        await client_over(handler, auth=BearerAuth("tok")).get_run_status("r")

        assert handler.requests[0].headers["Authorization"] == "Bearer tok"

    async def test_basic_header(self) -> None:
        handler = responder(200, RUN_STATUS)
        await client_over(handler, auth=BasicAuth("user", "pass")).get_run_status("r")

        assert handler.requests[0].headers["Authorization"].startswith("Basic ")

    def test_empty_service_key_is_rejected_at_construction(self) -> None:
        """
        An empty key must not become an empty header.

        A server whose own key was unset would authenticate it, so this fails at
        startup rather than becoming a silent hole.
        """
        with pytest.raises(ValueError):
            ServiceKeyAuth("")

    def test_empty_bearer_token_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            BearerAuth("")


class TestIdentityHeader:
    """X-On-Behalf-Of is sent only when asserted."""

    async def test_absent_by_default(self) -> None:
        handler = responder(200, RUN_STATUS)
        await client_over(handler).get_run_status("r")

        assert "X-On-Behalf-Of" not in handler.requests[0].headers

    async def test_sent_by_a_view(self) -> None:
        handler = responder(200, RUN_STATUS)
        await client_over(handler).on_behalf_of("alice").get_run_status("r")

        assert handler.requests[0].headers["X-On-Behalf-Of"] == "alice"

    async def test_views_do_not_leak_into_each_other(self) -> None:
        """
        Concurrent views on one pool keep separate identities.

        The failure this guards against is the worst kind for an audit trail: one
        user's request logged under another user's name.
        """
        handler = responder(200, RUN_STATUS)
        client = client_over(handler)

        await client.on_behalf_of("alice").get_run_status("r")
        await client.on_behalf_of("bob").get_run_status("r")
        await client.get_run_status("r")

        assert handler.requests[0].headers["X-On-Behalf-Of"] == "alice"
        assert handler.requests[1].headers["X-On-Behalf-Of"] == "bob"
        assert "X-On-Behalf-Of" not in handler.requests[2].headers

    async def test_blank_identity_is_not_sent(self) -> None:
        handler = responder(200, RUN_STATUS)
        await client_over(handler).on_behalf_of("   ").get_run_status("r")

        assert "X-On-Behalf-Of" not in handler.requests[0].headers


class TestRequestEncoding:
    """What the client puts on the wire for the trickier parameters."""

    async def test_prefix_is_added_once(self) -> None:
        handler = responder(200, RUN_STATUS)
        await client_over(handler).get_run_status("r")

        assert handler.requests[0].url.path == "/ga4gh/wes/v1/runs/r/status"

    async def test_base_url_path_is_preserved(self) -> None:
        """A service mounted under a sub-path is not clobbered by the prefix."""
        handler = responder(200, RUN_STATUS)
        http = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://gateway.test/wes"
        )
        await AsyncWesClient(http_client=http).get_run_status("r")

        assert handler.requests[0].url.path == "/wes/ga4gh/wes/v1/runs/r/status"

    async def test_unset_parameters_are_omitted(self) -> None:
        """
        An unset page_token is absent, not the string "None".

        Sending "None" would have WES treat it as a real continuation token.
        """
        handler = responder(200, {"runs": [], "next_page_token": None})
        await client_over(handler).list_runs(page_size=10)

        params = handler.requests[0].url.params
        assert "page_token" not in params
        assert "filters" not in params
        assert params["page_size"] == "10"

    async def test_filters_are_json_encoded(self) -> None:
        handler = responder(200, {"runs": []})
        await client_over(handler).list_runs(project="P-1", state="RUNNING", tags={"k": "v"})

        filters = json.loads(handler.requests[0].url.params["filters"])
        assert filters == {"project": "P-1", "state": "RUNNING", "tags": {"k": "v"}}

    async def test_enum_state_is_encoded_as_its_value(self) -> None:
        from wes_client import State

        handler = responder(200, {"runs": []})
        await client_over(handler).list_runs(state=State.COMPLETE)

        assert json.loads(handler.requests[0].url.params["filters"])["state"] == "COMPLETE"

    async def test_dict_form_fields_are_json_encoded(self) -> None:
        handler = responder(200, {"run_id": "r"})
        await client_over(handler).submit_run(
            workflow_url="wf",
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_params={"a": 1},
            tags={"ProjectId": "P-1"},
        )

        body = handler.requests[0].content.decode()
        assert "workflow_params" in body
        # The dict became a JSON string in the form field, not a repr.
        assert '"a"' in body or "%22a%22" in body

    async def test_prencoded_json_string_is_not_double_encoded(self) -> None:
        """
        A caller who already encoded a field gets it passed through.

        Double-encoding would send a JSON string containing JSON, and the server
        would parse it into a string rather than an object.
        """
        handler = responder(200, {"run_id": "r"})
        await client_over(handler).submit_run(
            workflow_url="wf",
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_params='{"a": 1}',
        )

        body = handler.requests[0].content.decode()
        assert "%5C%22" not in body  # no escaped quotes from a second encoding


class TestLifecycle:
    """Who owns the connection pool."""

    async def test_injected_client_is_not_closed(self) -> None:
        """
        An injected pool outlives the wrapper.

        APIServer builds its own httpx client in its lifespan; if aclose() here
        tore that down, a wrapper going out of scope would break the service.
        """
        http = httpx.AsyncClient(transport=httpx.MockTransport(responder(200, RUN_STATUS)))
        client = AsyncWesClient(http_client=http, base_url="http://wes.test")

        await client.aclose()
        assert not http.is_closed

        await http.aclose()

    async def test_owned_client_is_closed(self) -> None:
        client = AsyncWesClient("http://wes.test")
        await client.aclose()

        assert client._http.is_closed

    async def test_context_manager_closes(self) -> None:
        async with AsyncWesClient("http://wes.test") as client:
            http = client._http
        assert http.is_closed

    def test_base_url_is_required_without_an_injected_client(self) -> None:
        with pytest.raises(ValueError, match="base_url is required"):
            AsyncWesClient()


class TestPagination:
    """iter_runs against tokens a real server would not conveniently produce."""

    async def test_follows_tokens_to_the_end(self) -> None:
        pages = [
            {"runs": [{"run_id": "a"}, {"run_id": "b"}], "next_page_token": "2"},
            {"runs": [{"run_id": "c"}], "next_page_token": None},
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=pages[handler.calls])  # type: ignore[attr-defined]

        handler.calls = -1  # type: ignore[attr-defined]

        def counting(request: httpx.Request) -> httpx.Response:
            handler.calls += 1  # type: ignore[attr-defined]
            return handler(request)

        seen = [run.run_id async for run in client_over(counting).iter_runs()]
        assert seen == ["a", "b", "c"]

    async def test_stops_on_an_empty_page_despite_a_token(self) -> None:
        """
        A server that keeps returning a token cannot make this loop forever.

        Defensive, but the alternative failure is an unbounded loop holding a
        request open, which is far worse than returning early.
        """
        handler = responder(200, {"runs": [], "next_page_token": "always-more"})

        seen = [run async for run in client_over(handler).iter_runs()]

        assert seen == []
        assert len(handler.requests) == 1
