# GA4GH WES API Frontend Architecture

This document outlines the architecture and design for a comprehensive React-based frontend for the GA4GH Workflow Execution Service (WES) API with AWS HealthOmics integration.

## 1. Overview

The frontend will be a standalone React application that connects to the existing GA4GH WES API. It will provide a modern, user-friendly interface for submitting, monitoring, and managing workflow executions.

## 2. Technology Stack

### Frontend Framework
- **React 18+**: Modern React with hooks and functional components
- **Next.js 14**: For server-side rendering, API routes, and optimized production builds
- **TypeScript**: For type safety and better developer experience

### UI Components and Styling
- **Material UI (MUI) v5**: Popular React component library with a modern design system
- **Emotion**: For CSS-in-JS styling
- **React Query**: For efficient data fetching, caching, and state management
- **React Hook Form**: For form handling with validation

### Authentication
- **NextAuth.js**: For flexible authentication strategies
- **JWT**: For secure token-based authentication

### State Management
- **React Context API**: For global state management
- **React Query**: For server state management

### Development Tools
- **ESLint**: For code quality
- **Prettier**: For code formatting
- **Jest & React Testing Library**: For unit and component testing
- **Cypress**: For end-to-end testing

## 3. Application Architecture

### 3.1 Directory Structure

```
wes-frontend/
├── public/
│   ├── favicon.ico
│   └── assets/
├── src/
│   ├── components/
│   │   ├── common/
│   │   ├── dashboard/
│   │   ├── runs/
│   │   ├── submission/
│   │   └── logs/
│   ├── hooks/
│   │   ├── useAuth.ts
│   │   ├── useWesApi.ts
│   │   └── ...
│   ├── pages/
│   │   ├── _app.tsx
│   │   ├── index.tsx
│   │   ├── dashboard.tsx
│   │   ├── runs/
│   │   │   ├── index.tsx
│   │   │   └── [id].tsx
│   │   ├── submit.tsx
│   │   └── auth/
│   ├── services/
│   │   ├── api.ts
│   │   ├── auth.ts
│   │   └── ...
│   ├── types/
│   │   ├── wes.ts
│   │   └── ...
│   ├── utils/
│   │   ├── formatters.ts
│   │   └── ...
│   └── styles/
│       ├── theme.ts
│       └── globals.css
├── .eslintrc.js
├── .prettierrc
├── jest.config.js
├── next.config.js
├── package.json
└── tsconfig.json
```

### 3.2 Core Components

#### Layout Components
- `Layout`: Main application layout with navigation
- `Sidebar`: Navigation sidebar
- `Header`: Application header with user info and actions
- `Footer`: Application footer

#### Authentication Components
- `LoginForm`: User login interface
- `AuthGuard`: HOC to protect routes requiring authentication

#### Dashboard Components
- `Dashboard`: Main dashboard view
- `StatsSummary`: Summary of workflow statistics
- `RecentRuns`: List of recent workflow runs
- `StatusChart`: Visual representation of workflow statuses

#### Workflow Run Components
- `RunsList`: Paginated list of workflow runs with filtering
- `RunsFilter`: Filter and search interface for runs
- `RunCard`: Card view of a workflow run summary
- `RunDetails`: Detailed view of a specific run
- `TasksList`: List of tasks within a workflow run
- `TaskDetails`: Detailed view of a specific task

#### Workflow Submission Components
- `WorkflowSubmissionForm`: Form for submitting new workflows
- `ParameterInput`: Dynamic input for workflow parameters
- `FileUpload`: Component for uploading workflow files
- `TagsInput`: Component for adding tags to workflows

#### Log Viewer Components
- `LogViewer`: Component for viewing and searching logs
- `LogLine`: Individual log line with formatting
- `LogFilter`: Filter and search interface for logs

## 4. Key Features and Screens

### 4.1 Authentication

- User login/logout
- JWT-based authentication
- Role-based access control
- Integration with existing authentication systems (optional)

### 4.2 Dashboard

- Overview of workflow statistics
- Recent workflow runs
- Status distribution charts
- Quick access to common actions

### 4.3 Workflow Runs List

- Paginated list of all workflow runs
- Filtering by status, date, tags, etc.
- Sorting options
- Search functionality
- Bulk actions (cancel, delete)

### 4.4 Workflow Run Details

- Comprehensive view of a specific workflow run
- Status and timing information
- Input parameters
- Output files and results
- Task list with status indicators
- Access to logs
- Actions (cancel, rerun)

### 4.5 Task Details

- Detailed view of a specific task
- Status and timing information
- Command executed
- Resource usage
- Log viewer

### 4.6 Log Viewer

- Real-time log streaming (if supported)
- Log filtering and searching
- Syntax highlighting
- Download logs option
- Automatic scrolling

### 4.7 Workflow Submission

- Form for submitting new workflows
- Workflow type selection
- Parameter input with validation
- File upload for workflow definitions
- Tags and metadata input
- Submission confirmation

## 5. API Integration

### 5.1 WES API Endpoints

The frontend will integrate with the following GA4GH WES API endpoints:

- `GET /service-info`: Get service information
- `GET /runs`: List workflow runs
- `POST /runs`: Submit a new workflow run
- `GET /runs/{run_id}`: Get detailed information about a specific run
- `DELETE /runs/{run_id}`: Cancel a workflow run
- `GET /runs/{run_id}/status`: Get the status of a workflow run
- `GET /runs/{run_id}/logs`: Get the logs for a workflow run

### 5.2 API Client

A dedicated API client will be implemented to handle communication with the WES API:

```typescript
// Example API client structure
class WesApiClient {
  constructor(baseUrl, authToken) {
    this.baseUrl = baseUrl;
    this.authToken = authToken;
  }

  async getServiceInfo() { ... }
  async listRuns(params) { ... }
  async getRun(runId) { ... }
  async submitRun(workflowParams) { ... }
  async cancelRun(runId) { ... }
  async getRunStatus(runId) { ... }
  async getRunLogs(runId) { ... }
}
```

### 5.3 Data Fetching Strategy

- Use React Query for data fetching, caching, and state management
- Implement optimistic updates for better UX
- Handle pagination, filtering, and sorting on the client side when appropriate
- Implement error handling and retry logic

## 6. Authentication and Authorization

### 6.1 Authentication Flow

1. User navigates to the login page
2. User enters credentials
3. Frontend sends credentials to authentication endpoint
4. On successful authentication, JWT token is stored
5. Subsequent API requests include the JWT token
6. Token refresh mechanism to handle expiration

### 6.2 Authorization

- Role-based access control
- Permission-based UI rendering
- Secure route protection

## 7. User Experience Considerations

### 7.1 Responsive Design

- Mobile-first approach
- Responsive layouts for all screen sizes
- Touch-friendly interface

### 7.2 Accessibility

- WCAG 2.1 AA compliance
- Keyboard navigation
- Screen reader support
- Sufficient color contrast

### 7.3 Performance

- Code splitting and lazy loading
- Optimized bundle size
- Efficient rendering with React.memo and useMemo
- Debounced inputs for search and filtering

## 8. Development and Deployment

### 8.1 Development Workflow

1. Set up development environment with Next.js
2. Implement core components and pages
3. Connect to API endpoints
4. Implement authentication
5. Add advanced features
6. Testing and quality assurance

### 8.2 Deployment Options

- Static export for simple hosting
- Vercel for Next.js optimized hosting
- Docker container for custom deployment
- CI/CD pipeline integration

## 9. Future Enhancements

- Workflow visualization with task dependency graphs
- Advanced analytics and reporting
- Integration with workflow repositories
- Collaborative features (comments, sharing)
- Notification system
- Mobile application

## 10. Implementation Plan

### Phase 1: Foundation
- Set up Next.js project with TypeScript
- Implement basic layout and navigation
- Set up authentication
- Create core API services

### Phase 2: Core Features
- Implement dashboard
- Create workflow runs list with filtering
- Build workflow submission form
- Develop run details view

### Phase 3: Advanced Features
- Implement log viewer with real-time updates
- Add task details view
- Create visualization components
- Implement advanced filtering and search

### Phase 4: Polish and Optimization
- Improve UI/UX
- Optimize performance
- Add comprehensive error handling
- Implement accessibility features

### Phase 5: Testing and Deployment
- Unit and integration testing
- End-to-end testing
- Documentation
- Production deployment