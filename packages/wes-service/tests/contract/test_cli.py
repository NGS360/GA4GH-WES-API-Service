"""
CLI tests, driven against the real server through Typer's runner.

The CLI is a presentation layer, so most of it is covered by the client tests.
What is tested here is the logic that exists only in the CLI: argument parsing
into request shapes, the polling loop, and the exit codes shell callers branch on.

Requests go to the real WES app over httpx.ASGITransport, injected by pointing
WES_API_URL at a local server the fixture starts. Where that is impractical --
timeouts, sequences of changing states -- httpx.MockTransport stands in.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

from wes_client import cli

runner = CliRunner()


@pytest.fixture
def invoke(monkeypatch: pytest.MonkeyPatch) -> Any:
    """
    Run the CLI with a client wired to a given transport.

    Patches the client factory rather than the network, so argument parsing,
    output, and exit codes all run for real.
    """

    def _invoke(args: list[str], handler: Any) -> Any:
        monkeypatch.setenv("WES_API_URL", "http://wes.test")
        http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://wes.test")
        from wes_client import WesClient

        with patch.object(cli, "_client", return_value=WesClient(http_client=http)):
            return runner.invoke(cli.app, args)

    return _invoke


def recorder(*responses: httpx.Response) -> Any:
    """Return each response in turn, repeating the last, recording requests."""

    def handler(request: httpx.Request) -> httpx.Response:
        handler.requests.append(request)  # type: ignore[attr-defined]
        index = min(len(handler.requests) - 1, len(responses) - 1)  # type: ignore[attr-defined]
        return responses[index]

    handler.requests = []  # type: ignore[attr-defined]
    return handler


def status(state: str) -> httpx.Response:
    return httpx.Response(200, json={"run_id": "r1", "state": state})


class TestSubmitParams:
    """--param, and how it combines with --params."""

    def _submit(self, invoke: Any, *args: str) -> tuple[Any, dict]:
        handler = recorder(httpx.Response(200, json={"run_id": "new-run"}))
        result = invoke(
            ["runs", "submit", "--workflow-url", "wf-1", *args],
            handler,
        )
        body = handler.requests[0].content.decode() if handler.requests else ""
        # The form field carries JSON; pull it back out to assert on the values.
        params = {}
        for part in body.split("&"):
            if part.startswith("workflow_params="):
                from urllib.parse import unquote_plus

                params = json.loads(unquote_plus(part.split("=", 1)[1]))
        return result, params

    def test_single_param(self, invoke: Any) -> None:
        result, params = self._submit(invoke, "--param", "input_file=s3://bucket/a.fastq")

        assert result.exit_code == 0
        assert params == {"input_file": "s3://bucket/a.fastq"}

    def test_repeated_params(self, invoke: Any) -> None:
        result, params = self._submit(
            invoke, "--param", "a=s3://x", "--param", "b=s3://y"
        )

        assert result.exit_code == 0
        assert params == {"a": "s3://x", "b": "s3://y"}

    def test_values_are_typed_when_they_parse_as_json(self, invoke: Any) -> None:
        """
        A WDL input declared Int rejects the string "4", so numbers stay numbers.
        """
        _, params = self._submit(
            invoke, "--param", "threads=4", "--param", "paired=true", "--param", "ratio=0.5"
        )

        assert params == {"threads": 4, "paired": True, "ratio": 0.5}

    def test_non_json_values_stay_strings(self, invoke: Any) -> None:
        """Paths, URIs and identifiers are the common case and need no quoting."""
        _, params = self._submit(
            invoke,
            "--param", "path=s3://bucket/sample.fastq",
            "--param", "sample=NA12878",
            "--param", "ref=/data/ref.fa",
        )

        assert params == {
            "path": "s3://bucket/sample.fastq",
            "sample": "NA12878",
            "ref": "/data/ref.fa",
        }

    def test_value_may_contain_equals(self, invoke: Any) -> None:
        """Split on the first `=` only, so URIs and base64 survive."""
        _, params = self._submit(invoke, "--param", "query=a=1&b=2")

        assert params == {"query": "a=1&b=2"}

    def test_param_overrides_params_file(self, invoke: Any, tmp_path: Any) -> None:
        """The explicit flag wins over the file, so a loop can vary one input."""
        f = tmp_path / "inputs.json"
        f.write_text(json.dumps({"ref": "s3://ref.fa", "input_file": "s3://old"}))

        _, params = self._submit(
            invoke, "--params", str(f), "--param", "input_file=s3://new"
        )

        assert params == {"ref": "s3://ref.fa", "input_file": "s3://new"}

    def test_malformed_param_is_rejected(self, invoke: Any) -> None:
        handler = recorder(httpx.Response(200, json={"run_id": "x"}))
        result = invoke(
            ["runs", "submit", "--workflow-url", "wf-1", "--param", "no-equals-sign"], handler
        )

        assert result.exit_code == cli.EXIT_ERROR
        assert handler.requests == []  # nothing submitted

    def test_param_with_empty_key_is_rejected(self, invoke: Any) -> None:
        handler = recorder(httpx.Response(200, json={"run_id": "x"}))
        result = invoke(
            ["runs", "submit", "--workflow-url", "wf-1", "--param", "=value"], handler
        )

        assert result.exit_code == cli.EXIT_ERROR
        assert handler.requests == []

    def test_params_file_must_be_an_object(self, invoke: Any, tmp_path: Any) -> None:
        f = tmp_path / "inputs.json"
        f.write_text("[1, 2, 3]")

        handler = recorder(httpx.Response(200, json={"run_id": "x"}))
        result = invoke(
            ["runs", "submit", "--workflow-url", "wf-1", "--params", str(f)], handler
        )

        assert result.exit_code == cli.EXIT_ERROR
        assert handler.requests == []


class TestRunsWait:
    """The polling loop and what it exits with."""

    def test_returns_immediately_when_already_terminal(self, invoke: Any) -> None:
        handler = recorder(status("COMPLETE"))
        result = invoke(["runs", "wait", "r1"], handler)

        assert result.exit_code == 0
        assert len(handler.requests) == 1

    def test_polls_until_terminal(self, invoke: Any) -> None:
        handler = recorder(status("QUEUED"), status("RUNNING"), status("COMPLETE"))

        with patch.object(cli.time, "sleep") as sleep:
            result = invoke(["runs", "wait", "r1", "--interval", "0.01"], handler)

        assert result.exit_code == 0
        assert len(handler.requests) == 3
        assert sleep.call_count == 2

    def test_failed_run_exits_nonzero(self, invoke: Any) -> None:
        """
        So a shell script can stop on failure rather than carrying on.

        Only COMPLETE is success; every other terminal state is a failure here.
        """
        handler = recorder(status("EXECUTOR_ERROR"))
        result = invoke(["runs", "wait", "r1"], handler)

        assert result.exit_code == cli.EXIT_ERROR

    @pytest.mark.parametrize("state", ["EXECUTOR_ERROR", "SYSTEM_ERROR", "CANCELED", "PREEMPTED"])
    def test_every_non_complete_terminal_state_fails(self, invoke: Any, state: str) -> None:
        assert invoke(["runs", "wait", "r1"], recorder(status(state))).exit_code == cli.EXIT_ERROR

    def test_canceling_is_not_terminal(self, invoke: Any) -> None:
        """
        CANCELING still becomes CANCELED, so waiting must not stop on it.

        Treating it as terminal would report a run as finished while it is still
        winding down.
        """
        handler = recorder(status("CANCELING"), status("CANCELED"))

        with patch.object(cli.time, "sleep"):
            result = invoke(["runs", "wait", "r1", "--interval", "0.01"], handler)

        assert len(handler.requests) == 2
        assert result.exit_code == cli.EXIT_ERROR  # CANCELED is not success

    def test_timeout_has_its_own_exit_code(self, invoke: Any) -> None:
        """
        Distinguished from failure: a timeout says nothing about the outcome.

        A script that retries on timeout must not also retry a genuine failure.
        """
        handler = recorder(status("RUNNING"))

        result = invoke(
            ["runs", "wait", "r1", "--interval", "0.01", "--timeout", "0.001"], handler
        )

        assert result.exit_code == cli.EXIT_TIMEOUT

    def test_waits_for_several_runs(self, invoke: Any) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            handler.requests.append(request)  # type: ignore[attr-defined]
            run_id = str(request.url).rsplit("/", 2)[-2]
            # r1 finishes first; r2 needs another round.
            done = run_id == "r1" or len(handler.requests) > 2  # type: ignore[attr-defined]
            return httpx.Response(
                200, json={"run_id": run_id, "state": "COMPLETE" if done else "RUNNING"}
            )

        handler.requests = []  # type: ignore[attr-defined]

        with patch.object(cli.time, "sleep"):
            result = invoke(["runs", "wait", "r1", "r2", "--interval", "0.01"], handler)

        assert result.exit_code == 0
        # r1 polled once and then dropped from the loop, r2 polled twice.
        assert [str(r.url).rsplit("/", 2)[-2] for r in handler.requests] == ["r1", "r2", "r2"]

    def test_duplicate_run_ids_are_polled_once(self, invoke: Any) -> None:
        handler = recorder(status("COMPLETE"))
        result = invoke(["runs", "wait", "r1", "r1", "r1"], handler)

        assert result.exit_code == 0
        assert len(handler.requests) == 1

    def test_missing_run_reports_not_found(self, invoke: Any) -> None:
        handler = recorder(httpx.Response(404, json={"msg": "no such run", "status_code": 404}))
        result = invoke(["runs", "wait", "nope"], handler)

        assert result.exit_code == cli.EXIT_NOT_FOUND

    def test_zero_interval_is_rejected(self, invoke: Any) -> None:
        """Guards against a busy loop hammering the service."""
        handler = recorder(status("RUNNING"))
        result = invoke(["runs", "wait", "r1", "--interval", "0"], handler)

        assert result.exit_code == cli.EXIT_ERROR
        assert handler.requests == []


class TestAuthErrorAdvice:
    """
    401 and 403 need opposite advice.

    Both are WesAuthError and both exit 3, but a 401 means the service could not
    tell who is calling while a 403 means it could and refused. Suggesting
    credentials to someone who already has valid ones sends them to debug the
    wrong thing.
    """

    def test_401_suggests_setting_credentials(self, invoke: Any) -> None:
        handler = recorder(
            httpx.Response(401, json={"msg": "Not authenticated", "status_code": 401})
        )
        result = invoke(["runs", "get", "r1"], handler)

        assert result.exit_code == cli.EXIT_AUTH
        assert "WES_SERVICE_KEY" in result.output

    def test_403_points_at_ownership_instead(self, invoke: Any) -> None:
        handler = recorder(
            httpx.Response(403, json={"msg": "Not authorized to access this workflow run",
                                      "status_code": 403})
        )
        result = invoke(["runs", "get", "r1"], handler)

        assert result.exit_code == cli.EXIT_AUTH
        assert "on-behalf-of" in result.output
        assert "WES_SERVICE_KEY" not in result.output


class TestLauncherCommands:
    """--parent, `runs progress`, and `runs tree`."""

    def test_list_filters_by_parent(self, invoke: Any) -> None:
        """--parent goes out as the promoted parent_run_id filter, not as a tag."""
        handler = recorder(httpx.Response(200, json={"runs": [], "next_page_token": ""}))
        result = invoke(["runs", "list", "--parent", "launcher-1"], handler)

        assert result.exit_code == 0
        filters = json.loads(dict(handler.requests[0].url.params)["filters"])
        assert filters == {"parent_run_id": "launcher-1"}

    def test_progress_reports_counts(self, invoke: Any) -> None:
        handler = recorder(
            httpx.Response(
                200,
                json={
                    "run_id": "launcher-1",
                    "state": "RUNNING",
                    "children_total": 3,
                    "children_by_state": {"COMPLETE": 2, "RUNNING": 1, "QUEUED": 0},
                    "children_last_update": "2024-01-15T15:00:00Z",
                },
            )
        )
        result = invoke(["runs", "progress", "launcher-1"], handler)

        assert result.exit_code == 0
        assert handler.requests[0].url.path.endswith("/runs/launcher-1/progress")
        assert "3 child run(s)" in result.output
        assert "COMPLETE" in result.output
        # Unoccupied states are omitted rather than printed as zeroes.
        assert "QUEUED" not in result.output

    def test_progress_of_a_run_with_no_children(self, invoke: Any) -> None:
        """Every run answers this endpoint, so a plain run must not look like an error."""
        handler = recorder(
            httpx.Response(
                200,
                json={
                    "run_id": "r1",
                    "state": "COMPLETE",
                    "children_total": 0,
                    "children_by_state": {},
                    "children_last_update": None,
                },
            )
        )
        result = invoke(["runs", "progress", "r1"], handler)

        assert result.exit_code == 0
        assert "No child runs" in result.output

    def test_progress_of_a_missing_run_exits_not_found(self, invoke: Any) -> None:
        handler = recorder(httpx.Response(404, json={"msg": "no such run", "status_code": 404}))

        assert invoke(["runs", "progress", "nope"], handler).exit_code == cli.EXIT_NOT_FOUND

    def test_tree_lists_children(self, invoke: Any) -> None:
        """The launcher's status comes first, then one line per child."""

        def handler(request: httpx.Request) -> httpx.Response:
            handler.requests.append(request)  # type: ignore[attr-defined]
            if request.url.path.endswith("/status"):
                return httpx.Response(200, json={"run_id": "launcher-1", "state": "RUNNING"})
            return httpx.Response(
                200,
                json={
                    "runs": [
                        {"run_id": "c1", "state": "COMPLETE", "name": "sampleA"},
                        {"run_id": "c2", "state": "EXECUTOR_ERROR", "name": "sampleB"},
                    ],
                    "next_page_token": "",
                },
            )

        handler.requests = []  # type: ignore[attr-defined]

        result = invoke(["runs", "tree", "launcher-1"], handler)

        assert result.exit_code == 0
        assert "launcher-1" in result.output
        assert "sampleA" in result.output
        assert "sampleB" in result.output
        filters = json.loads(dict(handler.requests[1].url.params)["filters"])
        assert filters == {"parent_run_id": "launcher-1"}

    def test_tree_of_a_run_with_no_children(self, invoke: Any) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            handler.requests.append(request)  # type: ignore[attr-defined]
            if request.url.path.endswith("/status"):
                return httpx.Response(200, json={"run_id": "r1", "state": "COMPLETE"})
            return httpx.Response(200, json={"runs": [], "next_page_token": ""})

        handler.requests = []  # type: ignore[attr-defined]

        result = invoke(["runs", "tree", "r1"], handler)

        assert result.exit_code == 0
        assert "no child runs" in result.output
