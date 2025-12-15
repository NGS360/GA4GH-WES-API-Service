# GA4GH WES API Service - Architecture & Implementation Plan

## Executive Summary

This document outlines the architecture and implementation plan for a FastAPI-based GA4GH Workflow Execution Service (WES) API v1.1.0 compliant service. The implementation follows a separation-of-concerns design where the API service logs workflow requests to a database, and a separate daemon monitors and executes workflows.

## Technology Stack

- **Language**: Python 3.12
- **Web Framework**: FastAPI (async REST API)
- **Package Manager**: uv
- **Database**: MySQL with SQLAlchemy ORM
- **Migration Tool**: Alembic
- **Authentication**: Basic Auth (with OAuth2 hooks for future)
- **Storage**: Configurable (Local filesystem + S3)
- **Testing**: pytest
- **Validation**: Pydantic v2
- **Logging**: Python logging with structured output

## Project Structure

```
GA4GH-WES-API-Service/
├── src/
│   └── wes_service/
│       ├── __init__.py
│       ├── main.py                    # FastAPI app factory
│       ├── config.py                  # Configuration management
│       ├── api/
│       │   ├── __init__.py
│       │   ├── deps.py               # Dependency injection
│       │   ├── routes/
│       │   │   ├── __init__.py
│       │   │   ├── service_info.py   # /service-info endpoint
│       │   │   ├── runs.py           # /runs endpoints
│       │   │   └── tasks.py          # /runs/{id}/tasks endpoints
│       │   └── middleware/
│       │       ├── __init__.py
│       │       ├── auth.py           # Authentication middleware
│       │       └── error_handler.py  # Global error handling
│       ├── core/
│       │   ├── __init__.py
│       │   ├── security.py           # Auth utilities
│       │   └── storage.py            # Storage abstraction layer
│       ├── db/
│       │   ├── __init__.py
│       │   ├── base.py               # SQLAlchemy base
│       │   ├── session.py            # Database session management
│       │   └── models.py             # Database models
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── service_info.py       # ServiceInfo schemas
│       │   ├── run.py                # Run-related schemas
│       │   ├── task.py               # Task-related schemas
│       │   └── common.py             # Shared schemas (State, ErrorResponse)
│       ├── services/
│       │   ├── __init__.py
│       │   ├── run_service.py        # Run business logic
│       │   └── task_service.py       # Task business logic
│       └── daemon/
│           ├── __init__.py
│           ├── workflow_monitor.py   # Daemon main loop
│           └── executors/
│               ├── __init__.py
│               ├── base.py           # Base executor interface
│               └── local.py          # Local executor stub
├── tests/
│   ├── __init__.py
│   ├── conftest.py                   # pytest fixtures
│   ├── api/
│   │   └── test_*.py                 # API endpoint tests
│   ├── services/
│   │   └── test_*.py                 # Service layer tests
│   └── integration/
│       └── test_*.py                 # Integration tests
├── alembic/
│   ├── versions/                     # Migration scripts
│   └── env.py                        # Alembic configuration
├── scripts/
│   ├── wes_client.py                 # Example WES client
│   └── run_workflows.sh              # Example workflow submission
├── examples/
│   ├── workflows/                    # Example CWL/WDL files
│   └── inputs/                       # Example input parameters
├── .env.example                      # Environment variables template
├── pyproject.toml                    # uv/project configuration
├── alembic.ini                       # Alembic configuration
├── README.md                         # Updated usage guide
└── ARCHITECTURE.md                   # This document
```

## Core Components

### 1. Database Models

**Tables**:
- `workflow_runs`: Main workflow execution records
- `task_logs`: Individual task execution logs
- `workflow_attachments`: Uploaded workflow files
- `run_outputs`: Workflow output files

**Key Fields for `workflow_runs`**:
```python
- id (UUID, Primary Key)
- state (Enum: UNKNOWN, QUEUED, INITIALIZING, RUNNING, PAUSED, COMPLETE, EXECUTOR_ERROR, SYSTEM_ERROR, CANCELED, CANCELING, PREEMPTED)
- workflow_type (String: CWL, WDL)
- workflow_type_version (String)
- workflow_url (String)
- workflow_params (JSON)
- workflow_engine (String)
- workflow_engine_version (String)
- workflow_engine_parameters (JSON)
- tags (JSON)
- start_time (DateTime)
- end_time (DateTime)
- created_at (DateTime)
- updated_at (DateTime)
```

**Key Fields for `task_logs`**:
```python
- id (UUID, Primary Key)
- run_id (UUID, Foreign Key)
- name (String)
- cmd (JSON Array)
- start_time (DateTime)
- end_time (DateTime)
- stdout_url (String)
- stderr_url (String)
- exit_code (Integer)
- system_logs (JSON Array)
- tes_uri (String, nullable)
```

### 2. Pydantic Schemas

Based on the OpenAPI spec, implement all schema models:
- `ServiceInfo` (extends GA4GH service-info spec)
- `RunRequest` (workflow submission)
- `RunId` (workflow ID response)
- `RunStatus` (status information)
- `RunSummary` (summary with timing)
- `RunLog` (detailed run information)
- `RunListResponse` (paginated run list)
- `TaskLog` (task execution details)
- `TaskListResponse` (paginated task list)
- `State` (enum)
- `ErrorResponse` (error details)
- `DefaultWorkflowEngineParameter`
- `WorkflowTypeVersion`
- `WorkflowEngineVersion`

### 3. Storage Abstraction Layer

**Interface**:
```python
class StorageBackend(ABC):
    @abstractmethod
    async def upload_file(self, file: UploadFile, path: str) -> str
    
    @abstractmethod
    async def download_file(self, path: str) -> bytes
    
    @abstractmethod
    async def get_url(self, path: str) -> str
    
    @abstractmethod
    async def delete_file(self, path: str) -> bool
```

**Implementations**:
- `LocalStorageBackend`: Stores files in local directory
- `S3StorageBackend`: Stores files in S3 bucket

**Configuration**: Select backend via environment variable

### 4. API Endpoints

#### `/service-info` (GET)
- Returns service metadata
- Includes supported workflow types, versions, engines
- Reports filesystem protocols supported
- Provides auth instructions URL

#### `/runs` (GET)
- Lists workflow runs with pagination
- Query params: `page_size`, `page_token`
- Returns `RunListResponse` with run summaries
- Filters runs based on user permissions

#### `/runs` (POST)
- Submits new workflow for execution
- Accepts `multipart/form-data` with:
  - `workflow_params` (JSON string)
  - `workflow_type` (CWL/WDL)
  - `workflow_type_version`
  - `workflow_url`
  - `workflow_attachment[]` (optional binary files)
  - `tags` (JSON string)
  - `workflow_engine`
  - `workflow_engine_version`
  - `workflow_engine_parameters` (JSON string)
- Stages attachments to temporary/permanent storage
- Creates database record with `QUEUED` state
- Returns `RunId`

#### `/runs/{run_id}` (GET)
- Returns detailed `RunLog` for specific run
- Includes run request, state, outputs
- Provides task logs URL (deprecated: task_logs array)

#### `/runs/{run_id}/status` (GET)
- Returns lightweight `RunStatus`
- Fast status check without full log details

#### `/runs/{run_id}/tasks` (GET)
- Lists tasks for a workflow run with pagination
- Query params: `page_size`, `page_token`
- Returns `TaskListResponse`

#### `/runs/{run_id}/tasks/{task_id}` (GET)
- Returns detailed `TaskLog` for specific task
- Includes command, timing, logs, exit code

#### `/runs/{run_id}/cancel` (POST)
- Cancels running workflow
- Updates state to `CANCELING` then `CANCELED`
- Returns `RunId`

### 5. Authentication & Authorization

**Phase 1 - Basic Auth**:
- HTTP Basic Authentication
- Username/password validated against configuration or database
- Placeholder for OAuth2 token validation

**Phase 2 - OAuth2 (Future)**:
- Bearer token support
- JWT validation
- Scope-based permissions
- Integration with external identity providers

**Authorization**:
- User can only see/manage their own runs
- Optional admin role for viewing all runs
- Per-run access control via tags/metadata

### 6. Workflow Daemon (Stub Implementation)

**Purpose**: Separate process that monitors database for queued workflows and executes them.

**Components**:

```python
class WorkflowMonitor:
    """Main daemon loop"""
    async def run(self):
        while True:
            # Poll database for QUEUED runs
            # Dispatch to executor
            # Update run state
            await asyncio.sleep(5)
```

```python
class WorkflowExecutor(ABC):
    """Base executor interface"""
    @abstractmethod
    async def execute(self, run: WorkflowRun) -> None
        pass
```

```python
class LocalExecutor(WorkflowExecutor):
    """Stub local executor"""
    async def execute(self, run: WorkflowRun) -> None:
        # Update state to INITIALIZING
        # Update state to RUNNING
        # Simulate execution
        # Update state to COMPLETE/ERROR
        pass
```

**Implementation Plan**:
1. Create basic daemon structure
2. Implement database polling
3. Add state transition logging
4. Stub executor that simulates workflow execution
5. Document executor interface for future real implementations

### 7. Configuration Management

**Environment Variables**:
```bash
# Database
DATABASE_URL=mysql+aiomysql://user:pass@localhost/wes_db

# Storage
STORAGE_BACKEND=local  # or 's3'
LOCAL_STORAGE_PATH=/var/wes/storage
S3_BUCKET_NAME=wes-workflows
S3_REGION=us-east-1

# Authentication
AUTH_METHOD=basic  # or 'oauth2'
BASIC_AUTH_USERS=admin:hashedpassword

# Service
SERVICE_NAME=GA4GH WES Service
SERVICE_ORGANIZATION=Your Organization
AUTH_INSTRUCTIONS_URL=https://example.com/auth

# API
API_PREFIX=/ga4gh/wes/v1
CORS_ORIGINS=*

# Daemon
DAEMON_POLL_INTERVAL=5
DAEMON_MAX_CONCURRENT_RUNS=10
```

### 8. Error Handling

**Strategy**:
- Global exception handler middleware
- Structured error responses matching OpenAPI spec
- Logging of all errors with context
- Appropriate HTTP status codes

**Error Response Format**:
```json
{
  "msg": "Detailed error message",
  "status_code": 404
}
```

### 9. Testing Strategy

**Unit Tests**:
- Test each service function in isolation
- Mock database and storage layers
- Test schema validation

**Integration Tests**:
- Test API endpoints with test database
- Test file upload/download flows
- Test authentication

**End-to-End Tests**:
- Submit real workflows
- Verify state transitions
- Test cancellation

**Test Coverage Goal**: >80%

## Implementation Phases

### Phase 1: Foundation (Days 1-2)
- Set up project structure
- Configure uv and dependencies
- Create database models
- Set up Alembic migrations
- Implement configuration management

### Phase 2: Core API (Days 3-5)
- Implement Pydantic schemas
- Create storage abstraction layer
- Implement service-info endpoint
- Implement runs endpoints (GET, POST)
- Implement run detail endpoints (GET status, GET log)

### Phase 3: Tasks & Features (Days 6-7)
- Implement tasks endpoints
- Implement cancel endpoint
- Add basic authentication
- Create error handling middleware
- Add logging

### Phase 4: Daemon (Day 8)
- Create daemon structure
- Implement database polling
- Create executor interface
- Implement stub local executor
- Add daemon tests

### Phase 5: Testing & Documentation (Days 9-10)
- Write comprehensive tests
- Update README with setup instructions
- Create example client scripts
- Create example workflows
- Document API usage

## Design Decisions

### 1. Async/Await
Use FastAPI's async capabilities for I/O operations (database, file storage) to improve scalability.

### 2. Separation of Concerns
- **API Layer**: Routes, request/response handling
- **Service Layer**: Business logic
- **Data Layer**: Database models and queries
- **Storage Layer**: File handling abstraction

### 3. Database Choice
MySQL provides:
- Strong consistency
- Good performance for transactional workloads
- Wide deployment support
- JSON column support for flexible fields

### 4. Storage Abstraction
Allows switching between local and cloud storage without code changes, supporting different deployment scenarios.

### 5. Daemon Separation
Keeps API responsive while allowing long-running workflow execution in separate process with independent scaling.

### 6. UUID for Run IDs
UUIDs prevent enumeration attacks and allow distributed ID generation.

## Security Considerations

1. **File Upload Security**:
   - Validate file sizes
   - Scan for malicious content
   - Prevent path traversal in filenames
   - Isolate uploaded files per run

2. **Input Validation**:
   - Strict Pydantic schema validation
   - Sanitize workflow parameters
   - Validate workflow URLs

3. **Authentication**:
   - Secure password hashing (bcrypt/argon2)
   - Token expiration
   - Rate limiting on auth endpoints

4. **Authorization**:
   - User isolation for runs
   - Validate run ownership before operations
   - Audit logging

## Scalability Considerations

1. **Horizontal Scaling**:
   - Stateless API design
   - Multiple daemon instances with run locking
   - Shared database and storage

2. **Performance**:
   - Database indexing on run_id, state, created_at
   - Pagination for list endpoints
   - Async I/O throughout

3. **Monitoring**:
   - Health check endpoints
   - Metrics export (Prometheus format)
   - Structured logging

## OpenAPI Compliance

The implementation will strictly follow the provided `workflow_execution_service.openapi.yaml` specification:
- All endpoints implemented as specified
- Exact request/response schemas
- Proper HTTP status codes
- Complete error handling per spec

## Future Enhancements

1. **OAuth2 Integration**: Full bearer token support
2. **Real Executors**: CWL and WDL engine integrations
3. **TES Integration**: Task Execution Service support
4. **Workflow Visualization**: UI for monitoring runs
5. **Advanced Storage**: Support for additional protocols (gs://, synapse://)
6. **Metrics & Analytics**: Workflow execution statistics
7. **Job Queuing**: Advanced scheduling and prioritization
8. **Notifications**: Webhook support for state changes

## Diagram: System Architecture

```mermaid
graph TB
    Client[WES Client]
    API[FastAPI Service]
    DB[(MySQL Database)]
    Storage[Storage Backend]
    Daemon[Workflow Daemon]
    Executor[Workflow Executor]
    
    Client -->|HTTP/REST| API
    API -->|CRUD Operations| DB
    API -->|Upload/Download| Storage
    Daemon -->|Poll for QUEUED| DB
    Daemon -->|Execute| Executor
    Executor -->|Update State| DB
    Executor -->|Read/Write Files| Storage
```

## Diagram: Workflow Submission Flow

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant DB
    participant Storage
    participant Daemon
    
    Client->>API: POST /runs (multipart/form-data)
    API->>Storage: Upload workflow attachments
    Storage-->>API: File URLs
    API->>DB: Insert run record (state=QUEUED)
    DB-->>API: Run ID
    API-->>Client: Return RunId
    
    loop Daemon Poll
        Daemon->>DB: Query QUEUED runs
        DB-->>Daemon: Run list
        Daemon->>DB: Update state (INITIALIZING)
        Daemon->>Storage: Download workflow files
        Daemon->>DB: Update state (RUNNING)
        Note over Daemon: Execute workflow
        Daemon->>Storage: Upload outputs
        Daemon->>DB: Update state (COMPLETE)
    end
    
    Client->>API: GET /runs/{run_id}/status
    API->>DB: Query run
    DB-->>API: Run status
    API-->>Client: Return RunStatus
```

## Diagram: State Transitions

```mermaid
stateDiagram-v2
    [*] --> QUEUED: POST /runs
    QUEUED --> INITIALIZING: Daemon picks up
    INITIALIZING --> RUNNING: Workflow starts
    RUNNING --> COMPLETE: Success
    RUNNING --> EXECUTOR_ERROR: Workflow fails
    RUNNING --> SYSTEM_ERROR: System issue
    RUNNING --> CANCELING: POST /cancel
    CANCELING --> CANCELED: Cleanup done
    RUNNING --> PAUSED: Pause (optional)
    PAUSED --> RUNNING: Resume
    RUNNING --> PREEMPTED: System preemption
    COMPLETE --> [*]
    EXECUTOR_ERROR --> [*]
    SYSTEM_ERROR --> [*]
    CANCELED --> [*]
    PREEMPTED --> [*]
```

## Success Criteria

1. ✅ All API endpoints implemented per OpenAPI spec
2. ✅ Database models support all required fields
3. ✅ File upload/download working for both local and S3
4. ✅ Basic authentication functional
5. ✅ Daemon polls and updates run states
6. ✅ Comprehensive test coverage (>80%)
7. ✅ Documentation complete and accurate
8. ✅ Example client can submit workflows successfully

## Next Steps

After reviewing this architecture plan:
1. Confirm the approach meets your requirements
2. Address any concerns or modifications needed
3. Switch to Code mode to begin implementation
4. Start with Phase 1 (Foundation)