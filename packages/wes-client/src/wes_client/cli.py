"""
Command line interface for the WES client.

A presentation layer over WesClient and nothing more: it parses arguments,
resolves credentials from the environment, and formats what comes back. No HTTP
lives here. That is the point of building it on the same client the services use
-- when this repo changes an endpoint, the CLI and NGS360 APIServer both follow
from one edit, instead of the CLI keeping its own copy of the API that quietly
rots.

Requires the ``cli`` extra:

    uv pip install 'wes-client[cli]'

Configuration comes from the environment so that credentials never land in shell
history:

    WES_API_URL         Service root, e.g. http://localhost:8000
    WES_API_TOKEN       NGS360 API token           -> bearer auth
    WES_SERVICE_KEY     Internal service key       -> service-key auth
    WES_USERNAME        With WES_PASSWORD          -> basic auth
    WES_PASSWORD
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Annotated, Any

import httpx

try:
    import typer
    from rich.console import Console
    from rich.table import Table
except ImportError as exc:  # pragma: no cover - exercised by installing without the extra
    # [project.scripts] declares `wes` unconditionally, so the command exists even
    # when the cli extra was not installed. Without this it dies on a bare
    # ModuleNotFoundError that names typer and gives no hint that an extra is the
    # fix -- a confusing first encounter with the package for anyone who installed
    # it as a library and then tried the command.
    raise SystemExit(
        f"The 'wes' command needs the cli extra, which is not installed ({exc.name} is missing).\n"
        "  uv:  uv pip install 'wes-client[cli]'\n"
        "  pip: pip install 'wes-client[cli]'\n"
        "In this repo's workspace:  uv sync --all-packages --all-extras"
    ) from exc

from wes_schemas import TERMINAL_STATES, State
from wes_client import __version__
from wes_client.auth import BasicAuth, BearerAuth, ServiceKeyAuth
from wes_client.errors import WesAuthError, WesError, WesNotFound
from wes_client.sync_client import WesClient

app = typer.Typer(
    help="Interact with a GA4GH Workflow Execution Service.",
    no_args_is_help=True,
    add_completion=False,
)
runs_app = typer.Typer(help="Submit, inspect, and cancel workflow runs.", no_args_is_help=True)
tasks_app = typer.Typer(help="Inspect the tasks within a run.", no_args_is_help=True)
app.add_typer(runs_app, name="runs")
app.add_typer(tasks_app, name="tasks")

console = Console()
err_console = Console(stderr=True)

# Exit codes, so shell callers can branch without scraping stderr.
EXIT_ERROR = 1
EXIT_AUTH = 3
EXIT_NOT_FOUND = 4
EXIT_TIMEOUT = 5


def _resolve_auth() -> httpx.Auth | None:
    """
    Pick a credential from the environment.

    Ordered most specific to least. A service key outranks a user token because
    only a deliberately configured caller has one.
    """
    if key := os.environ.get("WES_SERVICE_KEY"):
        return ServiceKeyAuth(key)
    if token := os.environ.get("WES_API_TOKEN"):
        return BearerAuth(token)
    username = os.environ.get("WES_USERNAME")
    password = os.environ.get("WES_PASSWORD")
    if username and password:
        return BasicAuth(username, password)
    # None is valid: a service running with auth_method=none accepts it, and
    # failing here would make local development harder than the server does.
    return None


def _client(on_behalf_of: str | None = None) -> WesClient:
    """Build a client from the environment, or exit with a usable message."""
    base_url = os.environ.get("WES_API_URL")
    if not base_url:
        err_console.print(
            "[red]WES_API_URL is not set.[/red] Point it at the service root, "
            "e.g. [cyan]export WES_API_URL=http://localhost:8000[/cyan]"
        )
        raise typer.Exit(EXIT_ERROR)

    client = WesClient(base_url, auth=_resolve_auth(), user_agent=f"wes-cli/{__version__}")
    return client.on_behalf_of(on_behalf_of) if on_behalf_of else client


def _parse_pairs(entries: list[str] | None, flag: str) -> dict[str, str]:
    """
    Parse repeated KEY=VALUE options into a dict.

    Splits on the first `=` only, so values may contain them -- which matters for
    URIs and base64.
    """
    pairs: dict[str, str] = {}
    for entry in entries or []:
        if "=" not in entry:
            err_console.print(f"[red]{flag} must be KEY=VALUE, got {entry!r}[/red]")
            raise typer.Exit(EXIT_ERROR)
        key, value = entry.split("=", 1)
        if not key:
            err_console.print(f"[red]{flag} needs a key before the '=', got {entry!r}[/red]")
            raise typer.Exit(EXIT_ERROR)
        pairs[key] = value
    return pairs


def _decode_value(value: str) -> Any:
    """
    Interpret a --param value as JSON, falling back to the literal string.

    Types matter to the workflow engine: a WDL input declared Int rejects "4".
    Values that are not valid JSON -- paths, S3 URIs, sample names -- are left as
    strings, which is the common case and needs no quoting.
    """
    try:
        return json.loads(value)
    except ValueError:
        return value


def _emit(model: Any) -> None:
    """Print a model as indented JSON."""
    console.print_json(model.model_dump_json(exclude_none=True))


def _fail(exc: WesError) -> None:
    """Report a client error and exit with a code that distinguishes the cause."""
    err_console.print(f"[red]{exc}[/red]")
    if isinstance(exc, WesAuthError):
        # 401 and 403 both land here, but they need opposite advice. A 401 means
        # the service could not tell who is calling; a 403 means it could, and
        # said no. Telling someone to set credentials they have already set --
        # when the real problem is that they asked for another user's run --
        # sends them to debug the wrong thing.
        if exc.status_code == 403:
            err_console.print(
                "[dim]Authenticated, but not permitted. Runs are readable by the "
                "user who submitted them; check --on-behalf-of.[/dim]"
            )
        else:
            err_console.print(
                "[dim]Set WES_SERVICE_KEY, WES_API_TOKEN, or WES_USERNAME/WES_PASSWORD.[/dim]"
            )
        raise typer.Exit(EXIT_AUTH)
    if isinstance(exc, WesNotFound):
        raise typer.Exit(EXIT_NOT_FOUND)
    raise typer.Exit(EXIT_ERROR)


# -- runs -----------------------------------------------------------------


@runs_app.command("list")
def runs_list(
    project: Annotated[str | None, typer.Option(help="Filter to one project id.")] = None,
    state: Annotated[State | None, typer.Option(help="Filter to one workflow state.")] = None,
    task_name: Annotated[str | None, typer.Option(help="Filter on the TaskName tag.")] = None,
    parent: Annotated[
        str | None, typer.Option(help="Filter to the runs one launcher run submitted.")
    ] = None,
    limit: Annotated[int, typer.Option(help="Runs per page.")] = 20,
    all_pages: Annotated[
        bool, typer.Option("--all", help="Follow pagination and list every match.")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON instead of a table.")] = False,
    on_behalf_of: Annotated[
        str | None, typer.Option(help="Assert an acting user (service key only).")
    ] = None,
) -> None:
    """List workflow runs, newest first."""
    with _client(on_behalf_of) as client:
        try:
            if all_pages:
                runs = list(
                    client.iter_runs(
                        page_size=limit,
                        project=project,
                        state=state,
                        task_name=task_name,
                        parent_run_id=parent,
                    )
                )
                total: int | None = len(runs)
            else:
                page = client.list_runs(
                    page_size=limit,
                    project=project,
                    state=state,
                    task_name=task_name,
                    parent_run_id=parent,
                )
                runs = page.runs
                total = page.total_count
        except WesError as exc:
            _fail(exc)

    if as_json:
        console.print_json(json.dumps([run.model_dump(exclude_none=True) for run in runs]))
        return

    if not runs:
        console.print("[dim]No runs matched.[/dim]")
        return

    table = Table(title=f"{len(runs)} of {total if total is not None else len(runs)} runs")
    table.add_column("run_id", overflow="fold")
    table.add_column("state")
    table.add_column("name")
    table.add_column("project")
    table.add_column("started")
    table.add_column("submitted_by")
    for run in runs:
        table.add_row(
            run.run_id,
            run.state.value if run.state else "-",
            run.name or "-",
            run.project or "-",
            run.start_time or "-",
            run.submitted_by or "-",
        )
    console.print(table)


@runs_app.command("get")
def runs_get(
    run_id: str,
    on_behalf_of: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Show a run's full record."""
    with _client(on_behalf_of) as client:
        try:
            _emit(client.get_run(run_id))
        except WesError as exc:
            _fail(exc)


@runs_app.command("status")
def runs_status(
    run_id: str,
    on_behalf_of: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Show just a run's state."""
    with _client(on_behalf_of) as client:
        try:
            console.print(client.get_run_status(run_id).state or "UNKNOWN")
        except WesError as exc:
            _fail(exc)


@runs_app.command("progress")
def runs_progress(
    run_id: str,
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON instead of a table.")] = False,
    on_behalf_of: Annotated[str | None, typer.Option()] = None,
) -> None:
    """
    Show a launcher run's own state plus a rollup of the runs it submitted.

    The launcher's state is printed separately from the child counts because it
    is not an aggregate of them: a launcher that died while its children kept
    running shows a failed state above children still RUNNING, which is the
    condition worth seeing rather than averaging away.

    Any run works. One with no children reports zero counts.
    """
    with _client(on_behalf_of) as client:
        try:
            progress = client.get_run_progress(run_id)
        except WesError as exc:
            _fail(exc)

    if as_json:
        _emit(progress)
        return

    console.print(
        f"{progress.run_id} [cyan]{progress.state.value if progress.state else 'UNKNOWN'}[/cyan]"
    )
    if not progress.children_total:
        console.print("[dim]No child runs submitted by this run.[/dim]")
        return

    table = Table(title=f"{progress.children_total} child run(s)")
    table.add_column("state")
    table.add_column("count", justify="right")
    # Zero-count states are noise here; the launcher's whole vocabulary is nine
    # states and a run usually occupies two or three of them.
    for state_name, count in sorted(progress.children_by_state.items()):
        if count:
            table.add_row(state_name, str(count))
    console.print(table)
    if progress.children_last_update:
        console.print(f"[dim]last child update {progress.children_last_update}[/dim]")


@runs_app.command("tree")
def runs_tree(
    run_id: str,
    limit: Annotated[int, typer.Option(help="Children per page while paging.")] = 100,
    on_behalf_of: Annotated[str | None, typer.Option()] = None,
) -> None:
    """
    List the runs a launcher run submitted, one line each.

    Direct children only. A launcher that submitted another launcher shows that
    child here; run the command again on it to see the generation below.
    """
    with _client(on_behalf_of) as client:
        try:
            parent = client.get_run_status(run_id)
            children = list(client.iter_runs(page_size=limit, parent_run_id=run_id))
        except WesError as exc:
            _fail(exc)

    parent_state = parent.state.value if parent.state else "UNKNOWN"
    console.print(f"{parent.run_id} [cyan]{parent_state}[/cyan]")
    if not children:
        console.print("[dim]  (no child runs)[/dim]")
        return

    for index, child in enumerate(children):
        connector = "└─" if index == len(children) - 1 else "├─"
        state = child.state.value if child.state else "UNKNOWN"
        if child.state is State.COMPLETE:
            colour = "green"
        elif child.state in TERMINAL_STATES:
            # Terminal and not COMPLETE means this sample will not finish on its
            # own -- worth spotting in a hundred-line listing.
            colour = "red"
        else:
            colour = "cyan"
        console.print(
            f"{connector} {child.run_id} [{colour}]{state}[/{colour}] {child.name or '-'}"
        )


@runs_app.command("cancel")
def runs_cancel(
    run_id: str,
    on_behalf_of: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Cancel a run."""
    with _client(on_behalf_of) as client:
        try:
            canceled = client.cancel_run(run_id)
        except WesError as exc:
            _fail(exc)
    console.print(f"[green]canceled[/green] {canceled.run_id}")


@runs_app.command("submit")
def runs_submit(
    workflow_url: Annotated[str, typer.Option(help="Workflow URL, engine id, or attachment name.")],
    workflow_type: Annotated[str, typer.Option(help='Descriptor type: "CWL" or "WDL".')] = "CWL",
    workflow_type_version: Annotated[str, typer.Option(help="Descriptor version.")] = "v1.0",
    params: Annotated[
        Path | None, typer.Option(help="JSON file of workflow inputs.", exists=True)
    ] = None,
    param: Annotated[
        list[str] | None,
        typer.Option(help="Workflow input as KEY=VALUE. Repeatable. Overrides --params."),
    ] = None,
    tag: Annotated[
        list[str] | None,
        typer.Option(help="Tag as KEY=VALUE. Repeatable. NGS360 requires ProjectId."),
    ] = None,
    engine: Annotated[str | None, typer.Option(help='Engine, e.g. "awshealthomics".')] = None,
    engine_version: Annotated[str | None, typer.Option()] = None,
    attach: Annotated[
        list[Path] | None, typer.Option(help="File to upload. Repeatable.", exists=True)
    ] = None,
    on_behalf_of: Annotated[str | None, typer.Option()] = None,
) -> None:
    """
    Submit a workflow for execution.

    Inputs can come from a JSON file (--params), from individual --param
    KEY=VALUE pairs, or both, in which case --param wins for any key set twice.
    Individual pairs make submitting the same workflow over several inputs a
    plain shell loop, with no temporary JSON file per run.

    A --param value is decoded as JSON when it parses as JSON, so `threads=4`
    is the number 4 and `paired=true` is a boolean. Anything that is not valid
    JSON stays a string, which covers paths, URIs, and identifiers. Use --params
    when you need a string that would otherwise parse as a number.
    """
    tags = _parse_pairs(tag, "--tag")
    workflow_params: dict[str, Any] = {}

    if params is not None:
        try:
            loaded = json.loads(params.read_text())
        except ValueError as exc:
            err_console.print(f"[red]{params} is not valid JSON: {exc}[/red]")
            raise typer.Exit(EXIT_ERROR) from exc
        if not isinstance(loaded, dict):
            err_console.print(
                f"[red]{params} must contain a JSON object, "
                f"not a {type(loaded).__name__}[/red]"
            )
            raise typer.Exit(EXIT_ERROR)
        workflow_params.update(loaded)

    for key, value in _parse_pairs(param, "--param").items():
        workflow_params[key] = _decode_value(value)

    attachments = [(path.name, path.read_bytes()) for path in attach or []]

    with _client(on_behalf_of) as client:
        try:
            run = client.submit_run(
                workflow_url=workflow_url,
                workflow_type=workflow_type,
                workflow_type_version=workflow_type_version,
                workflow_params=workflow_params or None,
                tags=tags or None,
                workflow_engine=engine,
                workflow_engine_version=engine_version,
                attachments=attachments or None,
            )
        except WesError as exc:
            _fail(exc)
    console.print(f"[green]submitted[/green] {run.run_id}")


@runs_app.command("wait")
def runs_wait(
    run_ids: Annotated[list[str], typer.Argument(help="One or more run ids to wait for.")],
    interval: Annotated[float, typer.Option(help="Seconds between polls.")] = 10.0,
    timeout: Annotated[
        float, typer.Option(help="Give up after this many seconds. 0 waits indefinitely.")
    ] = 0.0,
    quiet: Annotated[bool, typer.Option("--quiet", help="Only print the final summary.")] = False,
    on_behalf_of: Annotated[str | None, typer.Option()] = None,
) -> None:
    """
    Poll runs until they reach a terminal state.

    Exits 0 only if every run finished COMPLETE, so this can gate a shell script:
    submit, wait, and stop if anything failed. A run that ends in any other
    terminal state exits 1; running out of time exits 5, which is distinguishable
    because a timeout says nothing about whether the work succeeded.

    Polls GetRunStatus rather than GetRunLog, which is the cheap endpoint -- but
    it is still one request per unfinished run per interval, so raise --interval
    when watching many runs or long ones.
    """
    if interval <= 0:
        err_console.print("[red]--interval must be greater than zero[/red]")
        raise typer.Exit(EXIT_ERROR)

    deadline = time.monotonic() + timeout if timeout > 0 else None
    pending = list(dict.fromkeys(run_ids))  # de-duplicate, keep order
    final: dict[str, State] = {}
    reported: dict[str, State] = {}

    with _client(on_behalf_of) as client:
        while pending:
            still_pending = []
            for run_id in pending:
                try:
                    state = client.get_run_status(run_id).state or State.UNKNOWN
                except WesError as exc:
                    _fail(exc)

                if state in TERMINAL_STATES:
                    # Not printed as progress: the summary below reports every
                    # run's final state, and printing here too would show an
                    # already-finished run twice.
                    final[run_id] = state
                    continue

                if not quiet and reported.get(run_id) != state:
                    console.print(f"{run_id} [cyan]{state.value}[/cyan]")
                    reported[run_id] = state
                still_pending.append(run_id)

            pending = still_pending
            if not pending:
                break

            if deadline is not None and time.monotonic() + interval > deadline:
                for run_id in pending:
                    console.print(f"{run_id} [yellow]still running[/yellow]")
                err_console.print(
                    f"[yellow]Timed out after {timeout:g}s with "
                    f"{len(pending)} run(s) unfinished.[/yellow]"
                )
                raise typer.Exit(EXIT_TIMEOUT)

            time.sleep(interval)

    failed = {rid: st for rid, st in final.items() if st is not State.COMPLETE}
    for run_id, state in final.items():
        colour = "green" if state is State.COMPLETE else "red"
        console.print(f"{run_id} [{colour}]{state.value}[/{colour}]")

    if failed:
        err_console.print(f"[red]{len(failed)} of {len(final)} run(s) did not complete.[/red]")
        raise typer.Exit(EXIT_ERROR)


# -- tasks ----------------------------------------------------------------


@tasks_app.command("list")
def tasks_list(
    run_id: str,
    limit: Annotated[int, typer.Option(help="Tasks per page.")] = 50,
    on_behalf_of: Annotated[str | None, typer.Option()] = None,
) -> None:
    """List the tasks executed as part of a run."""
    with _client(on_behalf_of) as client:
        try:
            response = client.list_tasks(run_id, page_size=limit)
        except WesError as exc:
            _fail(exc)

    if not response.task_logs:
        console.print("[dim]No tasks recorded for this run.[/dim]")
        return

    table = Table(title=f"tasks for {run_id}")
    table.add_column("id", overflow="fold")
    table.add_column("name")
    table.add_column("exit_code")
    table.add_column("started")
    table.add_column("ended")
    for task in response.task_logs:
        table.add_row(
            task.id,
            task.name or "-",
            "-" if task.exit_code is None else str(task.exit_code),
            task.start_time or "-",
            task.end_time or "-",
        )
    console.print(table)


@tasks_app.command("get")
def tasks_get(
    run_id: str,
    task_id: str,
    on_behalf_of: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Show one task's full record."""
    with _client(on_behalf_of) as client:
        try:
            _emit(client.get_task(run_id, task_id))
        except WesError as exc:
            _fail(exc)


# -- service --------------------------------------------------------------


@app.command("service-info")
def service_info() -> None:
    """Show the service's capabilities and current state counts."""
    with _client() as client:
        try:
            _emit(client.get_service_info())
        except WesError as exc:
            _fail(exc)


@app.command("version")
def version() -> None:
    """Show the client version."""
    console.print(__version__)


def main() -> None:
    """Console-script entry point."""
    try:
        app()
    except KeyboardInterrupt:
        # Ctrl-C during a long poll is a normal way to stop, not a crash worth a
        # traceback.
        err_console.print("[dim]interrupted[/dim]")
        sys.exit(130)


if __name__ == "__main__":
    main()
