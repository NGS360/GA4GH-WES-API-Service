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
    return this.apiClient.get<ServiceInfo>('/api/proxy?endpoint=service-info');
  }

  // List workflow runs with optional filtering
  async listRuns(params?: RunListParams): Promise<RunListResponse> {
    return this.apiClient.get<RunListResponse>('/api/proxy?endpoint=runs', { params });
  }

  // Get a specific run by ID
  async getRun(runId: string): Promise<RunResponse> {
    return this.apiClient.get<RunResponse>(`/api/proxy?endpoint=runs/${runId}`);
  }

  // Submit a new workflow run
  async submitRun(workflow: WorkflowSubmission): Promise<RunResponse> {
    return this.apiClient.post<RunResponse>('/api/proxy?endpoint=runs', workflow);
  }

  // Cancel a workflow run
  async cancelRun(runId: string): Promise<RunResponse> {
    return this.apiClient.delete<RunResponse>(`/api/proxy?endpoint=runs/${runId}`);
  }

  // Get the status of a workflow run
  async getRunStatus(runId: string): Promise<RunStatus> {
    return this.apiClient.get<RunStatus>(`/api/proxy?endpoint=runs/${runId}/status`);
  }

  // Get the logs for a workflow run
  async getRunLogs(runId: string): Promise<RunLogs> {
    return this.apiClient.get<RunLogs>(`/api/proxy?endpoint=runs/${runId}/logs`);
  }

  // Get log content from a log URL
  async fetchLogContent(logUrl: string): Promise<string> {
    // For CloudWatch logs, we might need a proxy endpoint
    if (logUrl.includes('cloudwatch')) {
      return this.apiClient.get<string>('/api/proxy/logs', { params: { url: logUrl } });
    }
    // For S3 or other directly accessible logs
    return this.apiClient.get<string>(logUrl, { 
      baseURL: '', // Override base URL to use the full log URL
      responseType: 'text'
    });
  }
}

export default WesService;

