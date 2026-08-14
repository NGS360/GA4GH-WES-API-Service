# wes-client

Client library and CLI for the GA4GH Workflow Execution Service, maintained
alongside the server it talks to.

## Why it lives in this repo

The team that owns the contract owns the client. A contract change and the client
change land in the same commit, and the contract tests run the client against the
real server app in this repo's CI — so a breaking change fails here, before any
consumer picks it up.

It is hand-written rather than generated. Generating from the server's own
OpenAPI document would mean round-tripping our pydantic models through JSON
Schema and back into a second, lookalike set of classes, losing validators along
the way and leaving `RunLog` meaning two different classes depending on which
side you're on. Instead both sides import `wes-schemas`, and a test asserts
every operation here matches a real path in the server's OpenAPI document — the
drift detection codegen would have given us, without the generated tree.

## Library use

```python
from wes_client import AsyncWesClient, ServiceKeyAuth, WesError, WesNotFound

client = AsyncWesClient("http://wes:8000", auth=ServiceKeyAuth(key))

# One client per process; `on_behalf_of` returns a cheap view sharing its pool.
runs = await client.on_behalf_of("alice").list_runs(project="P-123", page_size=10)
for run in runs.runs:
    print(run.run_id, run.state)

await client.aclose()
```

`WesClient` is the same surface without the awaits, over `httpx.Client`.

### Errors

Exceptions describe what happened to the call, not what you should return to
whoever asked you — see `errors.py`. Map them at your own edge:

```python
try:
    runs = await client.list_runs(project=project_id)
except WesNotFound:
    raise HTTPException(404, "No such project")
except WesError as exc:
    raise HTTPException(502, "Workflow service unavailable") from exc
```

### Testing against the real server

Pass a client wired to the server app and no socket is involved:

```python
transport = httpx.ASGITransport(app=create_app())
async with httpx.AsyncClient(transport=transport, base_url="http://wes") as http:
    client = AsyncWesClient(http_client=http)
    assert (await client.get_service_info()).workflow_type_versions
```

## CLI

The `cli` extra adds a `wes` command.

### Install

```bash
git clone https://github.com/NGS360/GA4GH-WES-API-Service.git
cd GA4GH-WES-API-Service
uv tool install './packages/wes-client[cli]'
```

`wes` is now on your `PATH` and runs from any directory.

### Update

```bash
git pull
uv tool install --reinstall './packages/wes-client[cli]'
```

Use `--reinstall`, not `--force`. `--force` replaces the tool's entry point but
leaves dependencies alone, so a changed `wes-schemas` whose version has not moved
is served from uv's build cache — even after an uninstall. The symptom is an
`ImportError` for something you just added.

### Uninstall

```bash
uv tool uninstall wes-client
```

### Or run it without installing

From the repo root:

```bash
uv sync --all-packages --all-extras
uv run wes runs list --limit 5
```

### Configure

```bash
export WES_API_URL=http://localhost:8000   # service root, without /ga4gh/wes/v1
export WES_SERVICE_KEY=...                 # or WES_API_TOKEN, or WES_USERNAME + WES_PASSWORD
```

### Examples

```bash
wes service-info
wes runs list --limit 5
wes runs list --project P-123 --state COMPLETE
wes runs list --limit 5 --json
wes runs get <run_id>
wes runs status <run_id>
wes runs cancel <run_id>
wes tasks list <run_id> --on-behalf-of alice
```

Submitting. `workflow_url` is an NGS360 catalog workflow id, optionally
`:version` — there is no engine prefix, and where the run executes comes from the
catalog:

```bash
wes runs submit --workflow-url fcf1b62cf3b44b549afd51c0318fc087 \
    --workflow-type WDL --workflow-type-version 1.0 \
    --param input_file=s3://bucket/sample.fastq \
    --tag ProjectId=P-123
```

Repeat `--param` for more inputs, or pass a JSON file with `--params` and use
`--param` to override individual keys. A `--param` value is decoded as JSON when
it parses as one, so `threads=4` is a number and `paired=true` a boolean;
anything else stays a string.

Waiting. `runs wait` polls until every run reaches a terminal state, and exits
non-zero unless they all finished `COMPLETE` — so a shell script can stop on
failure:

```bash
wes runs wait <run_id> <run_id> --interval 30 --timeout 3600
```

Together they cover fan-out over several inputs:

```bash
ids=()
for f in s3://bucket/a.fastq s3://bucket/b.fastq; do
    ids+=("$(wes runs submit --workflow-url fcf1b62cf3b44b549afd51c0318fc087 \
        --workflow-type WDL --workflow-type-version 1.0 \
        --param input_file="$f" --tag ProjectId=P-123 | awk '{print $NF}')")
done
wes runs wait "${ids[@]}"
```

Add `--help` to any command: `wes --help`, `wes runs --help`,
`wes runs submit --help`.

Exit codes: `0` success, `1` error, `3` auth, `4` not found, `5` wait timed out.
