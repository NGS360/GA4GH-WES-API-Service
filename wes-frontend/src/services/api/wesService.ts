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
