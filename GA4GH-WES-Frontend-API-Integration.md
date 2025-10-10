# GA4GH WES Frontend API Integration

This document outlines the API integration strategy for the GA4GH WES Frontend application, detailing how the React frontend will communicate with the WES API.

## 1. API Client Structure

The frontend will use a dedicated API client to handle all communication with the WES API. This client will be implemented using Axios for HTTP requests and will include features like request/response interceptors, error handling, and authentication.

### 1.1 Core API Client

```typescript
// src/services/api/apiClient.ts

import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse, AxiosError } from 'axios';
import { getAuthToken, refreshToken } from '../auth/authService';

class ApiClient {
  private client: AxiosInstance;
  private baseURL: string;

  constructor(baseURL: string) {
    this.baseURL = baseURL;
    this.client = axios.create({
      baseURL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.setupInterceptors();
  }

  private setupInterceptors(): void {
    // Request interceptor - add auth token
    this.client.interceptors.request.use(
      (config) => {
        const token = getAuthToken();
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Response interceptor - handle errors and token refresh
    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean };
        
        // Handle 401 Unauthorized - token expired
        if (error.response?.status === 401 && !originalRequest._retry) {
          originalRequest._retry = true;
          try {
            await refreshToken();
            const token = getAuthToken();
            this.client.defaults.headers.common.Authorization = `Bearer ${token}`;
            return this.client(originalRequest);
          } catch (refreshError) {
            // Redirect to login if refresh fails
            window.location.href = '/auth/login';
            return Promise.reject(refreshError);
          }
        }
        
        return Promise.reject(error);
      }
    );
  }

  async get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response: AxiosResponse<T> = await this.client.get(url, config);
    return response.data;
  }

  async post<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    const response: AxiosResponse<T> = await this.client.post(url, data, config);
    return response.data;
  }

  async put<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    const response: AxiosResponse<T> = await this.client.put(url, data, config);
    return response.data;
  }

  async delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response: AxiosResponse<T> = await this.client.delete(url, config);
    return response.data;
  }
}

export default ApiClient;
```

### 1.2 WES API Service

```typescript
// src/services/api/wesService.ts

import ApiClient from './apiClient';
import { 
  ServiceInfo, 
  RunListResponse, 
  RunResponse, 
  RunStatus, 
  RunLogs,
  RunListParams,
  WorkflowSubmission
} from '../../types/wes';

class WesService {
  private apiClient: ApiClient;

  constructor(baseURL: string) {
    this.apiClient = new ApiClient(baseURL);
  }

  // Get service information
  async getServiceInfo(): Promise<ServiceInfo> {
    return this.apiClient.get<ServiceInfo>('/service-info');
  }

  // List workflow runs with optional filtering
  async listRuns(params?: RunListParams): Promise<RunListResponse> {
    return this.apiClient.get<RunListResponse>('/runs', { params });
  }

  // Get a specific run by ID
  async getRun(runId: string): Promise<RunResponse> {
    return this.apiClient.get<RunResponse>(`/runs/${runId}`);
  }

  // Submit a new workflow run
  async submitRun(workflow: WorkflowSubmission): Promise<RunResponse> {
    return this.apiClient.post<RunResponse>('/runs', workflow);
  }

  // Cancel a workflow run
  async cancelRun(runId: string): Promise<RunResponse> {
    return this.apiClient.delete<RunResponse>(`/runs/${runId}`);
  }

  // Get the status of a workflow run
  async getRunStatus(runId: string): Promise<RunStatus> {
    return this.apiClient.get<RunStatus>(`/runs/${runId}/status`);
  }

  // Get the logs for a workflow run
  async getRunLogs(runId: string): Promise<RunLogs> {
    return this.apiClient.get<RunLogs>(`/runs/${runId}/logs`);
  }

  // Get log content from a log URL
  async fetchLogContent(logUrl: string): Promise<string> {
    // For CloudWatch logs, we might need a proxy endpoint
    if (logUrl.includes('cloudwatch')) {
      return this.apiClient.get<string>('/proxy/logs', { params: { url: logUrl } });
    }
    // For S3 or other directly accessible logs
    return this.apiClient.get<string>(logUrl, { 
      baseURL: '', // Override base URL to use the full log URL
      responseType: 'text'
    });
  }
}

export default WesService;
```

## 2. Type Definitions

TypeScript interfaces for the WES API responses and requests:

```typescript
// src/types/wes.ts

// Service Info
export interface ServiceInfo {
  workflow_type_versions: Record<string, WorkflowTypeVersion>;
  supported_wes_versions: string[];
  supported_filesystem_protocols: string[];
  workflow_engine_versions: Record<string, string>;
  default_workflow_engine_parameters: WorkflowEngineParameter[];
  system_state_counts: Record<string, number>;
  auth_instructions_url?: string;
  tags: Record<string, string>;
}

export interface WorkflowTypeVersion {
  workflow_type_version: string[];
  is_default: boolean;
}

export interface WorkflowEngineParameter {
  name: string;
  type: string;
  default_value?: string;
}

// Run List
export interface RunListResponse {
  runs: RunListItem[];
  next_page_token?: string;
}

export interface RunListItem {
  run_id: string;
  state: RunState;
}

// Run Details
export interface RunResponse {
  run_id: string;
  state: RunState;
  run_log: RunLog;
  task_logs: TaskLog[];
  outputs: Record<string, any>;
  request: WorkflowRequest;
}

export interface RunLog {
  name: string;
  cmd: string[];
  start_time: string;
  end_time: string;
  stdout: string;
  stderr: string;
  exit_code: number;
}

export interface TaskLog {
  name: string;
  cmd: string[];
  start_time: string;
  end_time: string;
  stdout: string;
  stderr: string;
  exit_code: number;
  stdout_url?: string;
  stderr_url?: string;
}

// Run Status
export interface RunStatus {
  run_id: string;
  state: RunState;
}

// Run Logs
export interface RunLogs {
  run_id: string;
  request: WorkflowRequest;
  state: RunState;
  run_log: RunLog;
  task_logs: TaskLog[];
  outputs: Record<string, any>;
}

// Workflow Request
export interface WorkflowRequest {
  workflow_params: Record<string, any>;
  workflow_type: string;
  workflow_type_version: string;
  workflow_url: string;
  workflow_engine_parameters?: Record<string, string>;
  tags?: Record<string, string>;
}

// Workflow Submission
export interface WorkflowSubmission {
  workflow_params: Record<string, any>;
  workflow_type: string;
  workflow_type_version: string;
  workflow_url: string;
  workflow_engine_parameters?: Record<string, string>;
  tags?: Record<string, string>;
}

// Run List Parameters
export interface RunListParams {
  page_size?: number;
  page_token?: string;
  state?: RunState;
  tag?: string;
  workflow_type?: string;
  workflow_type_version?: string;
  from_date?: string;
  to_date?: string;
}

// Run States
export enum RunState {
  UNKNOWN = 'UNKNOWN',
  QUEUED = 'QUEUED',
  INITIALIZING = 'INITIALIZING',
  RUNNING = 'RUNNING',
  PAUSED = 'PAUSED',
  COMPLETE = 'COMPLETE',
  EXECUTOR_ERROR = 'EXECUTOR_ERROR',
  SYSTEM_ERROR = 'SYSTEM_ERROR',
  CANCELED = 'CANCELED',
  CANCELING = 'CANCELING',
}
```

## 3. React Query Integration

The frontend will use React Query for data fetching, caching, and state management:

```typescript
// src/hooks/useWesApi.ts

import { useQuery, useMutation, useQueryClient, UseQueryOptions, UseMutationOptions } from 'react-query';
import WesService from '../services/api/wesService';
import { 
  ServiceInfo, 
  RunListResponse, 
  RunResponse, 
  RunStatus, 
  RunLogs,
  RunListParams,
  WorkflowSubmission
} from '../types/wes';

// Initialize the WES service
const wesService = new WesService(process.env.NEXT_PUBLIC_WES_API_URL || '/api');

// Query keys
export const queryKeys = {
  serviceInfo: 'serviceInfo',
  runs: 'runs',
  run: (id: string) => ['run', id],
  runStatus: (id: string) => ['runStatus', id],
  runLogs: (id: string) => ['runLogs', id],
  logContent: (url: string) => ['logContent', url],
};

// Service Info
export const useServiceInfo = (options?: UseQueryOptions<ServiceInfo>) => {
  return useQuery<ServiceInfo>(
    queryKeys.serviceInfo,
    () => wesService.getServiceInfo(),
    options
  );
};

// List Runs
export const useRunsList = (params?: RunListParams, options?: UseQueryOptions<RunListResponse>) => {
  return useQuery<RunListResponse>(
    [queryKeys.runs, params],
    () => wesService.listRuns(params),
    options
  );
};

// Get Run
export const useRun = (runId: string, options?: UseQueryOptions<RunResponse>) => {
  return useQuery<RunResponse>(
    queryKeys.run(runId),
    () => wesService.getRun(runId),
    {
      enabled: !!runId,
      ...options,
    }
  );
};

// Get Run Status
export const useRunStatus = (
  runId: string, 
  options?: UseQueryOptions<RunStatus> & { pollInterval?: number }
) => {
  const { pollInterval = 0, ...queryOptions } = options || {};
  
  return useQuery<RunStatus>(
    queryKeys.runStatus(runId),
    () => wesService.getRunStatus(runId),
    {
      enabled: !!runId,
      refetchInterval: pollInterval > 0 ? pollInterval : undefined,
      ...queryOptions,
    }
  );
};

// Get Run Logs
export const useRunLogs = (runId: string, options?: UseQueryOptions<RunLogs>) => {
  return useQuery<RunLogs>(
    queryKeys.runLogs(runId),
    () => wesService.getRunLogs(runId),
    {
      enabled: !!runId,
      ...options,
    }
  );
};

// Fetch Log Content
export const useLogContent = (logUrl: string, options?: UseQueryOptions<string>) => {
  return useQuery<string>(
    queryKeys.logContent(logUrl),
    () => wesService.fetchLogContent(logUrl),
    {
      enabled: !!logUrl,
      ...options,
    }
  );
};

// Submit Run
export const useSubmitRun = (options?: UseMutationOptions<RunResponse, Error, WorkflowSubmission>) => {
  const queryClient = useQueryClient();
  
  return useMutation<RunResponse, Error, WorkflowSubmission>(
    (workflow) => wesService.submitRun(workflow),
    {
      onSuccess: () => {
        // Invalidate runs list to refresh after submission
        queryClient.invalidateQueries(queryKeys.runs);
      },
      ...options,
    }
  );
};

// Cancel Run
export const useCancelRun = (options?: UseMutationOptions<RunResponse, Error, string>) => {
  const queryClient = useQueryClient();
  
  return useMutation<RunResponse, Error, string>(
    (runId) => wesService.cancelRun(runId),
    {
      onSuccess: (data, runId) => {
        // Invalidate specific run queries
        queryClient.invalidateQueries(queryKeys.run(runId));
        queryClient.invalidateQueries(queryKeys.runStatus(runId));
        queryClient.invalidateQueries(queryKeys.runs);
      },
      ...options,
    }
  );
};
```

## 4. Authentication Integration

The frontend will use NextAuth.js for authentication, which will be integrated with the API client:

```typescript
// src/services/auth/authService.ts

import { signIn, signOut, getSession } from 'next-auth/react';

// Get the current auth token
export const getAuthToken = (): string | null => {
  // This is a synchronous function that should return the token from storage
  // In a real app, you might use localStorage, cookies, or a state management solution
  const token = localStorage.getItem('auth_token');
  return token;
};

// Refresh the token
export const refreshToken = async (): Promise<void> => {
  // In a real app, this would call your refresh token endpoint
  const session = await getSession();
  if (session?.error === 'RefreshAccessTokenError') {
    // If refresh fails, sign out
    await signOut({ redirect: false });
    throw new Error('Failed to refresh token');
  }
  
  // Store the new token
  if (session?.accessToken) {
    localStorage.setItem('auth_token', session.accessToken as string);
  }
};

// Sign in
export const login = async (credentials: { username: string; password: string }): Promise<boolean> => {
  const result = await signIn('credentials', {
    ...credentials,
    redirect: false,
  });
  
  return result?.ok || false;
};

// Sign out
export const logout = async (): Promise<void> => {
  localStorage.removeItem('auth_token');
  await signOut({ redirect: false });
};
```

## 5. API Proxy for CORS and Authentication

To handle CORS issues and to proxy requests to external services (like CloudWatch logs), we'll set up API routes in Next.js:

```typescript
// src/pages/api/proxy/logs.ts

import type { NextApiRequest, NextApiResponse } from 'next';
import { getSession } from 'next-auth/react';
import axios from 'axios';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  // Check authentication
  const session = await getSession({ req });
  if (!session) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  const { url } = req.query;
  
  if (!url || typeof url !== 'string') {
    return res.status(400).json({ error: 'URL parameter is required' });
  }

  try {
    // For CloudWatch logs, we need to use AWS SDK or a special endpoint
    if (url.includes('cloudwatch')) {
      // This is a simplified example - in a real app, you'd use AWS SDK
      // to fetch CloudWatch logs using the log group and stream from the URL
      const logGroupMatch = url.match(/log-group\/([^\/]+)/);
      const logStreamMatch = url.match(/log-events\/([^\/]+)/);
      
      if (!logGroupMatch || !logStreamMatch) {
        return res.status(400).json({ error: 'Invalid CloudWatch URL format' });
      }
      
      const logGroup = decodeURIComponent(logGroupMatch[1]);
      const logStream = decodeURIComponent(logStreamMatch[1]);
      
      // Here you would use AWS SDK to fetch logs
      // For this example, we'll just return a placeholder
      return res.status(200).send(`Logs for ${logGroup}/${logStream}`);
    } 
    
    // For direct URLs (like S3)
    const response = await axios.get(url, { responseType: 'text' });
    return res.status(200).send(response.data);
  } catch (error) {
    console.error('Error fetching logs:', error);
    return res.status(500).json({ error: 'Failed to fetch logs' });
  }
}
```

## 6. Example Component Usage

Here's how these API integrations would be used in React components:

### 6.1 Dashboard with Runs List

```tsx
// src/components/dashboard/RunsList.tsx

import React, { useState } from 'react';
import { useRunsList } from '../../hooks/useWesApi';
import { RunListParams, RunState } from '../../types/wes';
import { 
  CircularProgress, 
  Table, 
  TableBody, 
  TableCell, 
  TableContainer, 
  TableHead, 
  TableRow,
  Paper,
  TablePagination,
  Chip
} from '@mui/material';
import { format } from 'date-fns';
import { Link } from 'next/link';

const RunsList: React.FC = () => {
  const [params, setParams] = useState<RunListParams>({
    page_size: 10,
    page_token: '',
  });
  
  const { data, isLoading, error } = useRunsList(params);
  
  const handleChangePage = (event: unknown, newPage: number) => {
    setParams(prev => ({
      ...prev,
      page_token: newPage > 0 && data?.next_page_token ? data.next_page_token : '',
    }));
  };
  
  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    setParams(prev => ({
      ...prev,
      page_size: parseInt(event.target.value, 10),
      page_token: '',
    }));
  };
  
  if (isLoading) {
    return <CircularProgress />;
  }
  
  if (error) {
    return <div>Error loading runs: {(error as Error).message}</div>;
  }
  
  return (
    <Paper>
      <TableContainer>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Run ID</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.runs.map((run) => (
              <TableRow key={run.run_id}>
                <TableCell>
                  <Link href={`/runs/${run.run_id}`}>{run.run_id}</Link>
                </TableCell>
                <TableCell>
                  <Chip 
                    label={run.state} 
                    color={
                      run.state === RunState.COMPLETE ? 'success' :
                      run.state === RunState.RUNNING ? 'primary' :
                      run.state === RunState.QUEUED ? 'warning' :
                      run.state.includes('ERROR') ? 'error' : 'default'
                    } 
                  />
                </TableCell>
                <TableCell>
                  <Link href={`/runs/${run.run_id}`}>View Details</Link>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination
        component="div"
        count={-1} // Unknown total count from API
        rowsPerPage={params.page_size || 10}
        page={params.page_token ? 1 : 0} // Simplified pagination
        onPageChange={handleChangePage}
        onRowsPerPageChange={handleChangeRowsPerPage}
        rowsPerPageOptions={[5, 10, 25, 50]}
        nextIconButtonProps={{
          disabled: !data?.next_page_token,
        }}
        backIconButtonProps={{
          disabled: !params.page_token,
        }}
      />
    </Paper>
  );
};

export default RunsList;
```

### 6.2 Run Details with Log Viewer

```tsx
// src/components/runs/RunDetails.tsx

import React, { useState } from 'react';
import { useRun, useRunStatus, useRunLogs, useCancelRun } from '../../hooks/useWesApi';
import { RunState } from '../../types/wes';
import { 
  Box, 
  Typography, 
  Tabs, 
  Tab, 
  Button, 
  CircularProgress,
  Alert,
  Paper,
  Chip
} from '@mui/material';
import LogViewer from '../logs/LogViewer';
import TasksList from '../tasks/TasksList';
import OutputsList from '../outputs/OutputsList';

interface RunDetailsProps {
  runId: string;
}

const RunDetails: React.FC<RunDetailsProps> = ({ runId }) => {
  const [activeTab, setActiveTab] = useState(0);
  
  // Get run details with 10-second polling for active runs
  const { data: run, isLoading: isLoadingRun } = useRun(runId);
  const { data: status } = useRunStatus(runId, { 
    pollInterval: run?.state === RunState.RUNNING || run?.state === RunState.QUEUED ? 10000 : 0,
  });
  const { data: logs } = useRunLogs(runId);
  
  const { mutate: cancelRun, isLoading: isCancelling } = useCancelRun();
  
  const handleCancelRun = () => {
    if (confirm('Are you sure you want to cancel this run?')) {
      cancelRun(runId);
    }
  };
  
  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue);
  };
  
  if (isLoadingRun) {
    return <CircularProgress />;
  }
  
  if (!run) {
    return <Alert severity="error">Run not found</Alert>;
  }
  
  const currentState = status?.state || run.state;
  const isActive = currentState === RunState.RUNNING || currentState === RunState.QUEUED;
  
  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography variant="h4">
          Run: {runId}
        </Typography>
        <Box>
          <Chip 
            label={currentState} 
            color={
              currentState === RunState.COMPLETE ? 'success' :
              currentState === RunState.RUNNING ? 'primary' :
              currentState === RunState.QUEUED ? 'warning' :
              currentState.includes('ERROR') ? 'error' : 'default'
            } 
            sx={{ mr: 1 }}
          />
          {isActive && (
            <Button 
              variant="contained" 
              color="error" 
              onClick={handleCancelRun}
              disabled={isCancelling}
            >
              {isCancelling ? <CircularProgress size={24} /> : 'Cancel Run'}
            </Button>
          )}
        </Box>
      </Box>
      
      <Paper sx={{ mb: 2 }}>
        <Tabs value={activeTab} onChange={handleTabChange}>
          <Tab label="Overview" />
          <Tab label="Tasks" />
          <Tab label="Logs" />
          <Tab label="Outputs" />
        </Tabs>
      </Paper>
      
      {activeTab === 0 && (
        <Box>
          <Typography variant="h6">Workflow Details</Typography>
          <Typography>Type: {run.request.workflow_type}</Typography>
          <Typography>Version: {run.request.workflow_type_version}</Typography>
          <Typography>URL: {run.request.workflow_url}</Typography>
          
          <Typography variant="h6" mt={2}>Parameters</Typography>
          <pre>{JSON.stringify(run.request.workflow_params, null, 2)}</pre>
          
          {run.request.tags && Object.keys(run.request.tags).length > 0 && (
            <>
              <Typography variant="h6" mt={2}>Tags</Typography>
              <Box>
                {Object.entries(run.request.tags).map(([key, value]) => (
                  <Chip key={key} label={`${key}: ${value}`} sx={{ mr: 1, mb: 1 }} />
                ))}
              </Box>
            </>
          )}
        </Box>
      )}
      
      {activeTab === 1 && (
        <TasksList tasks={logs?.task_logs || run.task_logs || []} />
      )}
      
      {activeTab === 2 && (
        <LogViewer 
          runId={runId} 
          stdout={run.run_log.stdout}
          stderr={run.run_log.stderr}
          stdoutUrl={run.run_log.stdout_url}
        />
      )}
      
      {activeTab === 3 && (
        <OutputsList outputs={run.outputs} />
      )}
    </Box>
  );
};

export default RunDetails;
```

### 6.3 Log Viewer Component

```tsx
// src/components/logs/LogViewer.tsx

import React, { useState, useEffect } from 'react';
import { useLogContent } from '../../hooks/useWesApi';
import { 
  Box, 
  Typography, 
  Paper, 
  TextField, 
  CircularProgress,
  Tabs,
  Tab,
  Button
} from '@mui/material';
import { Search as SearchIcon, Download as DownloadIcon } from '@mui/icons-material';

interface LogViewerProps {
  runId: string;
  stdout?: string;
  stderr?: string;
  stdoutUrl?: string;
}

const LogViewer: React.FC<LogViewerProps> = ({ runId, stdout, stderr, stdoutUrl }) => {
  const [activeTab, setActiveTab] = useState(0);
  const [searchTerm, setSearchTerm] = useState('');
  const [filteredLogs, setFilteredLogs] = useState<string[]>([]);
  
  // Fetch log content if URL is provided
  const { data: logContent, isLoading } = useLogContent(stdoutUrl || '', {
    enabled: !!stdoutUrl,
  });
  
  // Use either the fetched log content or the provided stdout
  const logs = logContent || stdout || '';
  
  // Split logs into lines and filter based on search term
  useEffect(() => {
    if (!logs) {
      setFilteredLogs([]);
      return;
    }
    
    const lines = logs.split('\n');
    
    if (!searchTerm) {
      setFilteredLogs(lines);
      return;
    }
    
    const filtered = lines.filter(line => 
      line.toLowerCase().includes(searchTerm.toLowerCase())
    );
    
    setFilteredLogs(filtered);
  }, [logs, searchTerm]);
  
  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue);
  };
  
  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(event.target.value);
  };
  
  const handleDownload = () => {
    const content = activeTab === 0 ? logs : stderr;
    const filename = activeTab === 0 ? `${runId}-stdout.log` : `${runId}-stderr.log`;
    
    const element = document.createElement('a');
    const file = new Blob([content || ''], { type: 'text/plain' });
    element.href = URL.createObjectURL(file);
    element.download = filename;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };
  
  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <Tabs value={activeTab} onChange={handleTabChange}>
          <Tab label="Standard Output" />
          <Tab label="Standard Error" disabled={!stderr} />
        </Tabs>
        
        <Box display="flex" alignItems="center">
          <TextField
            size="small"
            placeholder="Search logs..."
            value={searchTerm}
            onChange={handleSearchChange}
            InputProps={{
              startAdornment: <SearchIcon fontSize="small" />,
            }}
            sx={{ mr: 1 }}
          />
          <Button
            variant="outlined"
            startIcon={<DownloadIcon />}
            onClick={handleDownload}
          >
            Download
          </Button>
        </Box>
      </Box>
      
      <Paper 
        sx={{ 
          p: 2, 
          maxHeight: '60vh', 
          overflow: 'auto',
          backgroundColor: '#1e1e1e',
          color: '#f1f1f1',
          fontFamily: 'monospace',
          fontSize: '0.875rem',
          whiteSpace: 'pre-wrap',
        }}
      >
        {isLoading ? (
          <Box display="flex" justifyContent="center" p={4}>
            <CircularProgress />
          </Box>
        ) : activeTab === 0 ? (
          filteredLogs.length > 0 ? (
            filteredLogs.map((line, index) => (
              <div key={index} style={{ padding: '2px 0' }}>
                {line}
              </div>
            ))
          ) : (
            <Typography>No logs available</Typography>
          )
        ) : (
          <Typography>{stderr || 'No error logs available'}</Typography>
        )}
      </Paper>
    </Box>
  );
};

export default LogViewer;
```

## 7. Error Handling

The frontend will include comprehensive error handling for API requests:

```typescript
// src/utils/errorHandling.ts

import { AxiosError } from 'axios';
import { toast } from 'react-toastify';

// Error types
export enum ErrorType {
  NETWORK = 'NETWORK',
  AUTHENTICATION = 'AUTHENTICATION',
  AUTHORIZATION = 'AUTHORIZATION',
  NOT_FOUND = 'NOT_FOUND',
  VALIDATION = 'VALIDATION',
  SERVER = 'SERVER',
  UNKNOWN = 'UNKNOWN',
}

// Error response structure
export interface ApiErrorResponse {
  message: string;
  code?: string;
  details?: any;
}

// Classify error by type
export const getErrorType = (error: unknown): ErrorType => {
  if (error instanceof AxiosError) {
    if