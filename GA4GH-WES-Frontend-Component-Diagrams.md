# GA4GH WES Frontend Component Diagrams

This document provides visual representations of the component structure and data flow for the GA4GH WES API Frontend.

## Application Structure

```mermaid
graph TD
    A[App] --> B[Layout]
    B --> C[Header]
    B --> D[Sidebar]
    B --> E[Main Content]
    B --> F[Footer]
    
    E --> G[Dashboard]
    E --> H[Runs List]
    E --> I[Run Details]
    E --> J[Workflow Submission]
    E --> K[Log Viewer]
    
    H --> H1[RunsFilter]
    H --> H2[RunsList]
    H2 --> H3[RunCard]
    
    I --> I1[RunHeader]
    I --> I2[RunInfo]
    I --> I3[TasksList]
    I --> I4[OutputsList]
    I3 --> I5[TaskDetails]
    
    J --> J1[WorkflowTypeSelector]
    J --> J2[ParameterInputs]
    J --> J3[FileUploader]
    J --> J4[TagsInput]
    
    K --> K1[LogHeader]
    K --> K2[LogFilter]
    K --> K3[LogContent]
    K --> K4[LogDownload]
```

## Data Flow

```mermaid
graph LR
    A[User] --> B[UI Components]
    B --> C[React Hooks]
    C --> D[API Client]
    D --> E[WES API]
    E --> D
    D --> C
    C --> B
    B --> A
    
    F[Auth Provider] --> C
    G[React Query] --> C
    H[Context API] --> C
```

## Authentication Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant AuthAPI
    participant WESAPI
    
    User->>Frontend: Enter credentials
    Frontend->>AuthAPI: Login request
    AuthAPI->>Frontend: Return JWT token
    Frontend->>Frontend: Store token
    
    User->>Frontend: Request protected resource
    Frontend->>WESAPI: API request with token
    WESAPI->>Frontend: Return data
    Frontend->>User: Display data
    
    Note over Frontend,WESAPI: Token refresh happens automatically
```

## Workflow Submission Flow

```mermaid
sequenceDiagram
    participant User
    participant SubmissionForm
    participant ValidationService
    participant APIClient
    participant WESAPI
    
    User->>SubmissionForm: Fill workflow details
    SubmissionForm->>ValidationService: Validate inputs
    ValidationService->>SubmissionForm: Validation result
    
    alt is valid
        SubmissionForm->>APIClient: Submit workflow
        APIClient->>WESAPI: POST /runs
        WESAPI->>APIClient: Return run ID
        APIClient->>SubmissionForm: Submission success
        SubmissionForm->>User: Show success & run ID
    else is invalid
        SubmissionForm->>User: Show validation errors
    end
```

## Run Status Monitoring

```mermaid
graph TD
    A[Run Details Page] --> B[Initial Load]
    B --> C{Run Status}
    C -->|COMPLETE| D[Show Results]
    C -->|RUNNING| E[Poll for Updates]
    C -->|QUEUED| E
    C -->|ERROR| F[Show Error Details]
    
    E --> G[Update UI]
    G --> H{Status Changed?}
    H -->|Yes| C
    H -->|No| E
```

## Component Hierarchy for Run Details

```mermaid
graph TD
    A[RunDetailsPage] --> B[RunHeader]
    A --> C[RunTabs]
    
    C --> D[OverviewTab]
    C --> E[TasksTab]
    C --> F[LogsTab]
    C --> G[OutputsTab]
    
    D --> D1[RunMetadata]
    D --> D2[StatusTimeline]
    D --> D3[ParametersSummary]
    
    E --> E1[TasksList]
    E1 --> E2[TaskItem]
    E2 --> E3[TaskDetails]
    
    F --> F1[LogSelector]
    F --> F2[LogViewer]
    F2 --> F3[LogLine]
    
    G --> G1[OutputFiles]
    G --> G2[OutputMetadata]
```

## Dashboard Layout

```mermaid
graph TD
    A[Dashboard] --> B[StatsSummary]
    A --> C[StatusChart]
    A --> D[RecentRunsWidget]
    A --> E[QuickActions]
    
    B --> B1[TotalRuns]
    B --> B2[ActiveRuns]
    B --> B3[CompletedRuns]
    B --> B4[FailedRuns]
    
    C --> C1[PieChart]
    C --> C2[Legend]
    
    D --> D1[RunsList]
    D1 --> D2[RunItem]
    
    E --> E1[NewWorkflowButton]
    E --> E2[RefreshButton]
    E --> E3[FilterButton]
```

## Responsive Layout Behavior

```mermaid
graph TD
    A[Viewport Size] --> B{Size?}
    
    B -->|Desktop| C[Full Layout]
    B -->|Tablet| D[Condensed Layout]
    B -->|Mobile| E[Stacked Layout]
    
    C --> C1[Sidebar + Content]
    D --> D1[Collapsible Sidebar + Content]
    E --> E1[Bottom Navigation + Content]
    
    C1 --> F[Full Feature Set]
    D1 --> G[Adapted Feature Set]
    E1 --> H[Core Feature Set]
```

## API Integration Architecture

```mermaid
graph LR
    A[React Components] --> B[Custom Hooks]
    B --> C[React Query]
    C --> D[API Client]
    D --> E[Axios/Fetch]
    E --> F[WES API]
    
    G[Auth Provider] --> D
    H[Error Handler] --> D
    I[Request Interceptor] --> E
    J[Response Interceptor] --> E
```

## State Management

```mermaid
graph TD
    A[Application State] --> B[Server State]
    A --> C[UI State]
    A --> D[Auth State]
    
    B --> B1[React Query]
    B1 --> B2[Caching]
    B1 --> B3[Refetching]
    B1 --> B4[Mutations]
    
    C --> C1[React Context]
    C1 --> C2[Theme]
    C1 --> C3[Preferences]
    C1 --> C4[UI Settings]
    
    D --> D1[Auth Context]
    D1 --> D2[User Info]
    D1 --> D3[Permissions]
    D1 --> D4[Token Management]