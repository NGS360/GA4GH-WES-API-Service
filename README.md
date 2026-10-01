# GA4GH WES API Service

An implementation of the [GA4GH Workflow Execution Service (WES) API v1.1.0](https://github.com/ga4gh/workflow-execution-service-schemas)
specification using FastAPI and Python 3.12, backed by **AWS HealthOmics** with
**NGS360** as the workflow registry and identity provider.

## Overview

The service is a thin, standards-compliant façade. It records every run request
in MySQL, resolves the workflow and its inputs against NGS360, and hands
execution to an AWS Lambda function. It never talks to HealthOmics directly, and
it does not poll for status — HealthOmics state changes arrive as pushed
callbacks driven by EventBridge.

## How a run flows through the system

1. **Register the workflow in NGS360** (one-time, per workflow).
   `POST /api/v1/workflows` on the NGS360 API with
   `{name, definition_uri, engine, attributes...}`. NGS360 invokes a Lambda that
   imports the workflow into the backing engine (AWS HealthOmics) and records the
   resulting deployment.
2. **Submit a run** to `POST /ga4gh/wes/v1/runs` — from the NGS360 UI, from
   Launcher + [PAML](https://github.com/NGS360/PAML/), or from
   [`scripts/wes_client.py`](scripts/wes_client.py).
3. **WES records the request** in `workflow_runs` with state `QUEUED` and returns
   a `run_id` immediately.
4. **WES resolves the workflow** against NGS360 (version/alias → HealthOmics
   workflow ID), resolves any `ngs360://<file-id>` inputs to `s3://` URIs, and
   invokes the Lambda function asynchronously with `action: "submit_workflow"`.
5. **The Lambda function starts the HealthOmics run** via `StartRun`.
6. **HealthOmics emits status events to EventBridge**, which invokes the same
   Lambda function again — this time to report a state change. It POSTs to
   `/ga4gh/wes/v1/internal/callbacks/omics-state-change`, updating state,
   timestamps, outputs, and logs.
7. **Clients poll** `GET /runs/{run_id}/status` or `GET /runs/{run_id}` for the
   result.

One Lambda function serves both directions: WES invokes it to submit runs, and
EventBridge invokes it to deliver status changes back. `LAMBDA_FUNCTION_NAME`
names it.

```mermaid
graph LR
    C[Client<br/>NGS360 / PAML / CLI] -->|POST /runs| W[WES Service<br/>FastAPI]
    W --> DB[(MySQL)]
    W -->|resolve workflow + files| N[NGS360 API]
    W -->|invoke async<br/>submit_workflow| L[Lambda function]
    L -->|StartRun| O[AWS HealthOmics]
    O -->|status events| E[EventBridge]
    E -->|invoke| L
    L -->|POST /internal/callbacks| W
    C -->|GET /runs/id/status| W
```

## Features

- ✅ **GA4GH WES v1.1.0** — all 8 specified endpoints
- ✅ **FastAPI** — async throughout
- ✅ **SQLAlchemy 2.x async ORM** with MySQL (`aiomysql`)
- ✅ **Alembic migrations**
- ✅ **AWS HealthOmics execution** via an async Lambda invoke
- ✅ **Event-driven status updates** — EventBridge → Lambda → internal callback
  endpoint, with idempotency on the EventBridge event ID
- ✅ **NGS360 workflow resolution** — `workflow_url` accepts a workflow ID with
  an optional alias or version; the concrete version used is persisted in
  `resolved_workflow_version`
- ✅ **NGS360 file-ID inputs** — `ngs360://<file-id>` in `workflow_params` is
  resolved to its `s3://` URI at submission time
- ✅ **NGS360 token authentication** — bearer tokens validated against NGS360,
  with a TTL cache; the caller's token is forwarded on outbound NGS360 reads so
  they are attributed to the real user
- ✅ **HTTP Basic auth** as an alternative, bcrypt-hashed
- ✅ **Rich run filtering** — `GET /runs?filters={...}` over columns and JSON tags
- ✅ **Flexible attachment storage** — local filesystem or S3
- ✅ **AWS Secrets Manager** support for the DB URI and the callback API key
- ✅ **OpenAPI docs** — Swagger UI and ReDoc under the API prefix

See [docs/ARCHITECTURE.md §14](docs/ARCHITECTURE.md#14-known-gaps--limitations)
for known gaps, including the fact that `POST /runs/{id}/cancel` currently
updates only the database and does not stop the HealthOmics run.

## Quick Start

### Prerequisites

- Python 3.12+
- MySQL 8.0+ (SQLite is used for tests only)
- [uv](https://docs.astral.sh/uv/) package manager
- For real execution: AWS credentials with `lambda:InvokeFunction`, the deployed
  Lambda function, and a reachable NGS360 API

### Installation

```bash
git clone <repository-url>
cd GA4GH-WES-API-Service

# Install uv if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync --extra dev

# Configure
cp .env.example .env
$EDITOR .env
```

Create the database:

```bash
mysql -u root -p -e "CREATE DATABASE wes_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u root -p -e "CREATE USER 'wes_user'@'localhost' IDENTIFIED BY 'your_password';"
mysql -u root -p -e "GRANT ALL PRIVILEGES ON wes_db.* TO 'wes_user'@'localhost';"
```

Then apply migrations and start the service:

```bash
make migrate-upgrade      # uv run alembic upgrade head
make run                  # uv run python -m src.wes_service.main
```

The API is available at `http://localhost:8000`, docs at
`http://localhost:8000/ga4gh/wes/v1/docs`.

## Configuration

All configuration comes from environment variables. `.env` is loaded at import
time; see [`.env.example`](.env.example) for the full annotated list and
[docs/ARCHITECTURE.md §11](docs/ARCHITECTURE.md#11-configuration) for which
settings are actually consumed.

Values resolve in this order:

1. Environment variable
2. AWS Secrets Manager — if `ENV_SECRETS` names a secret (used for
   `SQLALCHEMY_DATABASE_URI` and `INTERNAL_CALLBACK_API_KEY` only)
3. The field default

### Database

```bash
SQLALCHEMY_DATABASE_URI=mysql+aiomysql://wes_user:wes_password@localhost:3306/wes_db
```

### NGS360

```bash
NGS360_API_URL=https://ngs360.example.com
```

Required for workflow resolution, `ngs360://` file resolution, and — with
`AUTH_METHOD=api_token` — token validation.

### Authentication

```bash
# Recommended: validate bearer tokens against NGS360
AUTH_METHOD=api_token
ENABLE_TOKEN_CACHE=true
TOKEN_CACHE_TTL_SECONDS=300
TOKEN_CACHE_MAX_SIZE=1000

# Alternative: HTTP Basic
AUTH_METHOD=basic
# Generate a hash:
#   python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('your_password'))"
BASIC_AUTH_USERS=admin:$2b$12$hashedpassword,user2:$2b$12$hashedpassword

# Development only
AUTH_METHOD=none
```

`AUTH_METHOD=oauth2` is accepted by config validation but is **not
implemented** — selecting it makes every request return 401.

With `AUTH_METHOD=basic` and an empty `BASIC_AUTH_USERS`, any username is
accepted. Do not deploy that.

### Execution (Lambda) and callbacks

```bash
LAMBDA_FUNCTION_NAME=ngs360-workflow-executor
LAMBDA_REGION=us-east-1

# Origin the Lambda function uses to reach this service. No trailing slash.
# Without it, runs stay QUEUED because the callback URL is relative.
CLIENT_ORIGIN=https://wes.example.com

ENABLE_CALLBACK_ENDPOINT=true
INTERNAL_CALLBACK_API_KEY=<shared secret, must match the Lambda function>
```

`LAMBDA_FUNCTION_NAME` and `LAMBDA_REGION` are read from the process environment
directly rather than through the `Settings` class, so they will not show up in
the startup settings log.

### Storage

`S3_BUCKET_NAME` serves two purposes: the bucket for workflow attachments (when
`STORAGE_BACKEND=s3`), and the prefix for HealthOmics outputs, which are written
to `s3://{S3_BUCKET_NAME}/Project/{ProjectId}/` regardless of backend.

```bash
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=/var/wes/storage

# or
STORAGE_BACKEND=s3
S3_BUCKET_NAME=wes-workflows
S3_REGION=us-east-1
S3_ACCESS_KEY_ID=       # blank = default boto3 credential chain
S3_SECRET_ACCESS_KEY=
```

### Secrets Manager

```bash
ENV_SECRETS=ngs360/wes/prod
AWS_REGION=us-east-1
```

## API Endpoints

Mounted under `API_PREFIX` (default `/ga4gh/wes/v1`).

### GA4GH WES

| Method | Path | Operation |
| ------ | ---- | --------- |
| GET  | `/service-info` | Service metadata and run-state counts |
| GET  | `/runs` | List runs (pagination + filtering) |
| POST | `/runs` | Submit a workflow |
| GET  | `/runs/{run_id}` | Full run log |
| GET  | `/runs/{run_id}/status` | Compact `{run_id, state}` |
| POST | `/runs/{run_id}/cancel` | Request cancellation (owner only) |
| GET  | `/runs/{run_id}/tasks` | List tasks |
| GET  | `/runs/{run_id}/tasks/{task_id}` | Task detail |

### Local extensions

| Method | Path | Notes |
| ------ | ---- | ----- |
| POST | `/ga4gh/wes/v1/internal/callbacks/omics-state-change` | Requires `X-Internal-API-Key`. See [docs/NGS360-Integration.md](docs/NGS360-Integration.md#6-inbound-state-change-callback) |
| GET  | `/ga4gh/wes/v1/internal/callbacks/health` | Unauthenticated |
| GET  | `/healthcheck` | `{"status": "healthy"}` |
| GET  | `/ga4gh/wes/v1/docs`, `/redoc`, `/openapi.json` | Interactive docs |

## Usage Examples

### Submit a workflow

`workflow_url` is an **NGS360 workflow ID**, optionally suffixed with an alias or
a version: `NGS360WORKFLOWID[:ALIAS_OR_VERSION]`. It is not an HTTP URL and has
no `omics:` prefix.

A `ProjectId` tag is **required** — submission fails without it.

```bash
curl -X POST "http://localhost:8000/ga4gh/wes/v1/runs" \
  -H "Authorization: Bearer $NGS360_TOKEN" \
  -F "workflow_type=WDL" \
  -F "workflow_type_version=1.0" \
  -F "workflow_url=wf-abc123:latest" \
  -F 'workflow_params={"fastq1":"s3://my-bucket/SampleA_R1.fastq.gz","reference":"s3://my-refs/hg38.fa"}' \
  -F 'workflow_engine_parameters={"name":"WGS-alignment","storageType":"DYNAMIC"}' \
  -F 'tags={"ProjectId":"P-0000000-0001","TaskName":"WGS-alignment"}'
```

```json
{ "run_id": "5b2f8c5a-1e9c-4b1f-8a7e-3d6e2a1c0fab" }
```

Inputs can also be given as NGS360 file IDs, resolved to S3 at submission:

```bash
  -F 'workflow_params={"fastq1":"ngs360://3f2a1b4c-8d9e-4f01-a234-56789abcdef0"}'
```

A `200` means **the request was recorded**, not that the workflow started. If
NGS360 resolution fails, the run is set to `SYSTEM_ERROR` with the reason in
`system_logs` — always check the run state.

### Check status

```bash
curl -H "Authorization: Bearer $NGS360_TOKEN" \
  "http://localhost:8000/ga4gh/wes/v1/runs/$RUN_ID/status"
```

### List and filter runs

```bash
curl -H "Authorization: Bearer $NGS360_TOKEN" -G \
  --data-urlencode 'filters={"state":"RUNNING","tags":{"ProjectId":"P-0000000-0001"}}' \
  "http://localhost:8000/ga4gh/wes/v1/runs?page_size=50"
```

### Cancel a run

```bash
curl -X POST -H "Authorization: Bearer $NGS360_TOKEN" \
  "http://localhost:8000/ga4gh/wes/v1/runs/$RUN_ID/cancel"
```

Only the user who submitted a run may cancel it. Note the current limitation:
this sets the run to `CANCELING` in the database but does not stop the
HealthOmics run.

For the full user-facing guide see
[docs/GA4GH-WES-HealthOmics-Guide.md](docs/GA4GH-WES-HealthOmics-Guide.md).

## Development

```bash
make test        # uv sync --extra dev && uv run pytest --cov=src --cov-report=html
make lint        # uv run flake8 .
make run         # uv run python -m src.wes_service.main
make build       # refresh uv.lock + requirements.txt and commit them
```

CI (`.github/workflows/cicd.yml`) runs `flake8` and the test suite with coverage
on pushes to `main` and on pull requests.

`pyproject.toml` also carries `[tool.ruff]` and `[tool.mypy]` sections, but
neither tool is a declared dependency and neither runs in CI. flake8
(`.flake8`) and pylint (`.pylintrc`) are the configs actually in use.

### Database migrations

```bash
make migrate-new message="add my column"   # autogenerate a revision
make migrate-upgrade                       # alembic upgrade head
make migrate-rollback                      # alembic downgrade -1
make migrate-current                       # show current revision
make migrate-empty message="data backfill" # empty revision
```

Current head: `dd9d7ebae80e` (adds `resolved_workflow_version`).

## Production Deployment

The [`Procfile`](Procfile) is the deployment entrypoint:

```
web: gunicorn src.wes_service.main:app --workers 4 \
     --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 \
     --timeout 120 --access-logfile - --error-logfile -
```

`make run` / `python -m src.wes_service.main` starts uvicorn with `reload=True`
and is for development only.

The service is stateless apart from the per-process token cache, so it scales
horizontally. Two consequences of running multiple workers:

- A revoked NGS360 token stays valid for up to `TOKEN_CACHE_TTL_SECONDS` on each
  worker.
- Migrations must be applied out of band (`make migrate-upgrade`); the app does
  not run them at startup.

### Behind Nginx

```nginx
server {
    listen 80;
    server_name wes.example.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Restrict `/ga4gh/wes/v1/internal/` at the proxy or security-group layer — the
callback API key is the only thing guarding it, and it can set arbitrary state on
any run.

## Project Structure

```
GA4GH-WES-API-Service/
├── src/wes_service/
│   ├── main.py                        # App factory, CORS, routers, /healthcheck
│   ├── config.py                      # Settings + AWS Secrets Manager fallback
│   ├── api/
│   │   ├── deps.py                    # DatabaseSession, CurrentUser, CurrentToken, Storage
│   │   ├── routes/                    # service_info, runs, tasks, callbacks
│   │   └── middleware/                # error_handler, response_formatter
│   ├── core/
│   │   ├── security.py                # Basic + NGS360 token auth, token cache
│   │   ├── callback_auth.py           # X-Internal-API-Key verification
│   │   └── storage.py                 # Local + S3 backends
│   ├── db/                            # base, models, session
│   ├── schemas/                       # service_info, run, task, callback, common
│   └── services/
│       ├── run_service.py
│       ├── task_service.py
│       ├── workflow_submission_service.py   # NGS360 resolution + Lambda invoke
│       └── callback_service.py              # State-change reconciliation
├── alembic/versions/                  # 6 migrations
├── tests/{api,core,services,integration}/
├── scripts/wes_client.py              # Reference client + CLI
├── examples/{workflows,inputs}/
├── docs/                              # See below
├── Makefile
├── Procfile
└── workflow_execution_service.openapi.yaml
```

## Documentation

| Document | Contents |
| -------- | -------- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Current architecture, request flows, DB schema, config reference, known gaps |
| [docs/NGS360-Integration.md](docs/NGS360-Integration.md) | NGS360 API contracts, Lambda payload, callback protocol, deployment checklist |
| [docs/GA4GH-WES-HealthOmics-Guide.md](docs/GA4GH-WES-HealthOmics-Guide.md) | User guide: submitting, monitoring, retrieving outputs |
| [docs/aws_omics_usage.md](docs/aws_omics_usage.md) | AWS-side configuration notes |
| [docs/Running_Specific_HealthOmics_Workflows.md](docs/Running_Specific_HealthOmics_Workflows.md) | Batch submission examples |

## Supported Workflow Types

- ✅ CWL — v1.0, v1.1, v1.2
- ✅ WDL — 1.0, draft-2

`workflow_type` is validated against the keys of
`Settings.get_workflow_type_versions()`, i.e. exactly `CWL` and `WDL`. The
workflow must have been imported into HealthOmics in that language; the actual
engine is chosen by the NGS360 deployment record, not by this field.

## Troubleshooting

### Run stuck in `QUEUED`

Most often the Lambda never ran or never called back. Check, in order:

1. `GET /runs/{id}` → `system_logs` for an NGS360 resolution error.
2. `LAMBDA_FUNCTION_NAME` is set and the service role may invoke it.
3. `CLIENT_ORIGIN` is set to a reachable origin — otherwise `callback_url` is
   relative and the Lambda function cannot reach this service.
4. `INTERNAL_CALLBACK_API_KEY` matches on both sides (a mismatch shows as 403s
   in this service's logs).
5. The Lambda function's CloudWatch logs — both the submit invocation and the
   EventBridge-triggered one land in the same log group.

### `SYSTEM_ERROR` immediately after submission

NGS360 resolution failed. `system_logs` names the cause: unknown workflow ID,
alias/version not found, no `AWSHealthOmics (us-east)` deployment, or an
unresolvable `ngs360://` file ID.

### 500 on submit with "ProjectId tag is required"

Add `ProjectId` to the `tags` JSON. This is a client error reported as 500.

### 401 on every request

If `AUTH_METHOD=oauth2`, that path is unimplemented — use `api_token` or
`basic`. Otherwise confirm the scheme matches: `api_token` needs
`Authorization: Bearer`, `basic` needs `-u user:pass`.

### Database connection errors

```bash
systemctl status mysql
mysql -u wes_user -p -h localhost wes_db
```

### Storage permission errors

```bash
chmod 755 /var/wes/storage
chown -R wes:wes /var/wes/storage
```

## Contributing

1. Create a feature branch off `main`.
2. Keep `make lint` and `make test` green.
3. Any schema change needs an Alembic revision off the current head.
4. Changes to a cross-process contract (NGS360 fields, Lambda payload, callback
   schema) need a matching update in
   [docs/NGS360-Integration.md](docs/NGS360-Integration.md).
5. Open a pull request.

## License

MIT — see the LICENSE file.

## Authors

- Ryan Golhar <ryan.golhar@bms.com>
- Maggie Chen <yu.chen2@bms.com>

## Acknowledgments

- [GA4GH](https://www.ga4gh.org/) for the WES specification
- [FastAPI](https://fastapi.tiangolo.com/) and [SQLAlchemy](https://www.sqlalchemy.org/)

## Support

- GA4GH WES spec: https://github.com/ga4gh/workflow-execution-service-schemas
- PAML: https://github.com/NGS360/PAML/
