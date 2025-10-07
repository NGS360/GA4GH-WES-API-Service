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
  stdout_url?: string;
  stderr_url?: string;
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
