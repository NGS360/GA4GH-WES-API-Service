# GA4GH WES API Service

A production-ready implementation of the [GA4GH Workflow Execution Service (WES) API v1.1.0](https://github.com/ga4gh/workflow-execution-service-schemas) specification using FastAPI and Python 3.12 backed by AWS HealthOmics.

## Overview

GA4GH WES is designed with a clean separation: the API service logs workflow requests to a database, while a separate daemon monitors requests and handles execution on the target platform. This implementation provides a robust, scalable foundation for workflow execution services.


## Expectations on how this works

1. Workflow is registered with NGS360, which then in turn registers the workflow with the backend service (in this case AWS HealthOmics).
   a. To register a workflow, make a call to NGS360 API Service, POST /api/v1/workflows, JSON={name='workflow_name', definition_uri='uri of workflow', engine='engine (AWS HealthOmics, SevenBridges, Arvados, etc', attributes=...}.
   
3. Workflow is submitted to GA4GH WES API via Launcher which uses PAML.
4. GA4GH WES API logs workflow in DB.
5. Daemon (lambda) submits workflow to AWS HealthOmics and updates db status info
6. Lambda is notiified when workflow completes and updates db info
7. Launcher queries GA4GH WES API via PAML.

## Features

- ✅ **Complete GA4GH WES v1.1.0 API** - All 8 endpoints implemented
- ✅ **FastAPI** - Modern, fast, async web framework
- ✅ **SQLAlchemy** - Async database ORM with MySQL support
- ✅ **Flexible Storage** - Local filesystem or AWS S3
- ✅ **Authentication** - HTTP Basic Auth with OAuth2 hooks
- ✅ **Database Migrations** - Alembic for version control
- ✅ **Workflow Monitoring** - Separate daemon for execution
- ✅ **OpenAPI Documentation** - Auto-generated API docs
- ✅ **Production Ready** - Error handling, logging, CORS

## Architecture

```
┌─────────────┐      REST API      ┌──────────────┐
│   Client    │ ───────────────────>│  FastAPI     │
│             │                     │  Service     │
└─────────────┘                     └──────┬───────┘
                                           │
                                           ↓
                                    ┌──────────────┐
                                    │   MySQL      │
                                    │   Database   │
                                    └──────┬───────┘
                                           ↑
                                           │
                                    ┌──────────────┐
                                    │   Workflow   │
                                    │   Daemon     │
                                    └──────┬───────┘
                                           │
                                    ┌──────────────┐
                                    │   Storage    │
                                    │  (Local/S3)  │
                                    └──────────────┘
```
## Quick Start

### Prerequisites

- Python 3.12+
- MySQL 8.0+
- uv package manager (recommended) or pip

### Installation

1. **Clone the repository**

```bash
git clone <repository-url>
cd GA4GH-WES-API-Service
```

2. **Install uv (if not already installed)**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

3. **Install dependencies**

```bash
uv sync
```

4. **Set up environment variables**

```bash
cp .env.example .env
# Edit .env with your configuration
```

5. **Configure database**

```bash
# Create MySQL database
mysql -u root -p -e "CREATE DATABASE wes_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u root -p -e "CREATE USER 'wes_user'@'localhost' IDENTIFIED BY 'your_password';"
mysql -u root -p -e "GRANT ALL PRIVILEGES ON wes_db.* TO 'wes_user'@'localhost';"

# Update SQLALCHEMY_DATABASE_URI in .env
# SQLALCHEMY_DATABASE_URI=mysql+aiomysql://wes_user:your_password@localhost:3306/wes_db
```

6. **Run database migrations**

```bash
uv run alembic upgrade head
```

7. **Start the API service**

```bash
uv run python -m src.wes_service.main
```

8. **Start the workflow daemon** (in a separate terminal)
   ```bash
   uv run python -m src.wes_service.daemon.workflow_monitor
   ```

The API will be available at `http://localhost:8000`

## Configuration

All configuration is managed through environment variables. Copy `.env.example` to `.env` and customize:

### Database Configuration
```bash
SQLALCHEMY_DATABASE_URI=mysql+aiomysql://wes_user:wes_password@localhost:3306/wes_db
```

### Storage Configuration
```bash
# Local storage
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=/var/wes/storage

# OR S3 storage
STORAGE_BACKEND=s3
S3_BUCKET_NAME=wes-workflows
S3_REGION=us-east-1
S3_ACCESS_KEY_ID=your_access_key
S3_SECRET_ACCESS_KEY=your_secret_key
```

### Authentication Configuration
```bash
AUTH_METHOD=basic  # or 'oauth2' or 'none'

# For basic auth, generate password hash:
# python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('your_password'))"
BASIC_AUTH_USERS=admin:$2b$12$hashedpassword,user2:$2b$12$hashedpassword
```

### Service Configuration
```bash
SERVICE_NAME=GA4GH WES Service
SERVICE_ORGANIZATION_NAME=Your Organization
SERVICE_ENVIRONMENT=production
API_PREFIX=/ga4gh/wes/v1
PORT=8000
```

## API Endpoints

### Service Information
- `GET /ga4gh/wes/v1/service-info` - Get service metadata

### Workflow Runs
- `GET /ga4gh/wes/v1/runs` - List workflow runs
- `POST /ga4gh/wes/v1/runs` - Submit new workflow
- `GET /ga4gh/wes/v1/runs/{run_id}` - Get run details
- `GET /ga4gh/wes/v1/runs/{run_id}/status` - Get run status
- `POST /ga4gh/wes/v1/runs/{run_id}/cancel` - Cancel run

### Tasks
- `GET /ga4gh/wes/v1/runs/{run_id}/tasks` - List tasks
- `GET /ga4gh/wes/v1/runs/{run_id}/tasks/{task_id}` - Get task details

### Additional Endpoints
- `GET /healthcheck` - Health check
- `GET /ga4gh/wes/v1/docs` - Swagger UI documentation
- `GET /ga4gh/wes/v1/redoc` - ReDoc documentation

## Usage Examples

### Submit a Workflow

```bash
curl -X POST "http://localhost:8000/ga4gh/wes/v1/runs" \
  -u admin:password \
  -F "workflow_type=CWL" \
  -F "workflow_type_version=v1.0" \
  -F "workflow_url=https://example.com/workflow.cwl" \
  -F "workflow_params={\"input_file\": \"s3://bucket/input.txt\"}" \
  -F "tags={\"project\": \"test\"}"
```

### List Runs

```bash
curl -X GET "http://localhost:8000/ga4gh/wes/v1/runs?page_size=10" \
  -u admin:password
```

### Get Run Status

```bash
curl -X GET "http://localhost:8000/ga4gh/wes/v1/runs/{run_id}/status" \
  -u admin:password
```

### Cancel a Run

```bash
curl -X POST "http://localhost:8000/ga4gh/wes/v1/runs/{run_id}/cancel" \
  -u admin:password
```

## Development

### Running Tests

```bash
# Install dev dependencies
uv sync --dev

# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=html
```

### Code Quality

```bash
# Format code
uv run ruff format src tests

# Lint code
uv run ruff check src tests

# Type checking
uv run mypy src
```

### Database Migrations

```bash
# Create a new migration
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head

# Rollback one migration
uv run alembic downgrade -1

# View migration history
uv run alembic history
```

## Production Deployment

### Using Docker (Recommended)

```bash
# Build image
docker build -t wes-service .

# Run with docker-compose
docker-compose up -d
```

### Using systemd

1. Create service file `/etc/systemd/system/wes-api.service`:
```ini
[Unit]
Description=GA4GH WES API Service
After=network.target mysql.service

[Service]
Type=simple
User=wes
WorkingDirectory=/opt/wes-service
Environment="PATH=/opt/wes-service/.venv/bin"
ExecStart=/opt/wes-service/.venv/bin/python -m src.wes_service.main
Restart=always

[Install]
WantedBy=multi-user.target
```

2. Create daemon service file `/etc/systemd/system/wes-daemon.service`:
```ini
[Unit]
Description=GA4GH WES Workflow Daemon
After=network.target mysql.service

[Service]
Type=simple
User=wes
WorkingDirectory=/opt/wes-service
Environment="PATH=/opt/wes-service/.venv/bin"
ExecStart=/opt/wes-service/.venv/bin/python -m src.wes_service.daemon.workflow_monitor
Restart=always

[Install]
WantedBy=multi-user.target
```

3. Enable and start services:
```bash
sudo systemctl enable wes-api wes-daemon
sudo systemctl start wes-api wes-daemon
```

### Using Nginx as Reverse Proxy

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

## Project Structure

```
GA4GH-WES-API-Service/
├── src/
│   └── wes_service/
│       ├── __init__.py
│       ├── main.py                    # FastAPI app factory
│       ├── config.py                  # Configuration management
│       ├── api/
│       │   ├── deps.py               # Dependency injection
│       │   ├── routes/               # API endpoints
│       │   │   ├── service_info.py
│       │   │   ├── runs.py
│       │   │   └── tasks.py
│       │   └── middleware/           # Error handlers
│       ├── core/
│       │   ├── security.py           # Authentication
│       │   └── storage.py            # Storage backends
│       ├── db/
│       │   ├── base.py               # SQLAlchemy base
│       │   ├── models.py             # Database models
│       │   └── session.py            # DB session
│       ├── schemas/                  # Pydantic models
│       ├── services/                 # Business logic
│       └── daemon/                   # Workflow daemon
├── alembic/                          # Database migrations
├── tests/                            # Test suite
├── pyproject.toml                    # Project dependencies
├── .env.example                      # Environment template
└── README.md                         # This file
```

## Workflow Engines

The current implementation includes:
- A stub local executor for demonstration
- AWS Omics integration for running workflows on AWS HealthOmics

To integrate additional workflow engines:

1. **Create a new executor** in `src/wes_service/daemon/executors/`
2. **Implement the `WorkflowExecutor` interface**
3. **Configure the daemon** to use your executor

Example executors:
- `LocalExecutor` - Stub implementation for demonstration
- `OmicsExecutor` - For AWS HealthOmics workflows
- `CWLToolExecutor` - For Common Workflow Language (to be implemented)
- `CromwellExecutor` - For WDL workflows (to be implemented)
- `NextflowExecutor` - For Nextflow pipelines (to be implemented)

For AWS Omics usage instructions, see [docs/aws_omics_usage.md](docs/aws_omics_usage.md).

## Supported Workflow Types

- ✅ CWL (Common Workflow Language) - v1.0, v1.1, v1.2
- ✅ WDL (Workflow Description Language) - 1.0, draft-2
- 🔄 Custom types can be added via configuration

## Troubleshooting

### Database Connection Errors
```bash
# Check MySQL is running
systemctl status mysql

# Test connection
mysql -u wes_user -p -h localhost wes_db
```

### Storage Permission Errors
```bash
# For local storage, ensure directory is writable
chmod 755 /var/wes/storage
chown -R wes:wes /var/wes/storage
```

### Authentication Issues
```bash
# Generate new password hash
python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('newpassword'))"
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Authors

- Ryan Golhar <ryan.golhar@bms.com>
- Maggie Chen <yu.chen2@bms.com>
- Claude 4.5 Sonnet (AI Assistant)

## Acknowledgments

- [GA4GH](https://www.ga4gh.org/) for the WES specification
- [FastAPI](https://fastapi.tiangolo.com/) framework
- [SQLAlchemy](https://www.sqlalchemy.org/) ORM

## Support

For issues and questions:
- GitHub Issues: [repository-url]/issues
- Documentation: [repository-url]/wiki
- GA4GH WES Spec: https://github.com/ga4gh/workflow-execution-service-schemas
