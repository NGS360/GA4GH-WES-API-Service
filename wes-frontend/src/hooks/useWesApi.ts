import { useQuery, useMutation, useQueryClient, UseQueryOptions, UseMutationOptions } from '@tanstack/react-query';
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
  return useQuery<ServiceInfo>({
    queryKey: [queryKeys.serviceInfo],
    queryFn: () => wesService.getServiceInfo(),
    ...options,
  });
};

// List Runs
export const useRunsList = (params?: RunListParams, options?: UseQueryOptions<RunListResponse>) => {
  return useQuery<RunListResponse>({
    queryKey: [queryKeys.runs, params],
    queryFn: () => wesService.listRuns(params),
    ...options,
  });
};

// Get Run
export const useRun = (runId: string, options?: UseQueryOptions<RunResponse>) => {
  return useQuery<RunResponse>({
    queryKey: queryKeys.run(runId),
    queryFn: () => wesService.getRun(runId),
    enabled: !!runId,
    ...options,
  });
};

// Get Run Status
export const useRunStatus = (
  runId: string, 
  options?: UseQueryOptions<RunStatus> & { pollInterval?: number }
) => {
  const { pollInterval = 0, ...queryOptions } = options || {};
  
  return useQuery<RunStatus>({
    queryKey: queryKeys.runStatus(runId),
    queryFn: () => wesService.getRunStatus(runId),
    enabled: !!runId,
    refetchInterval: pollInterval > 0 ? pollInterval : undefined,
    ...queryOptions,
  });
};

// Get Run Logs
export const useRunLogs = (runId: string, options?: UseQueryOptions<RunLogs>) => {
  return useQuery<RunLogs>({
    queryKey: queryKeys.runLogs(runId),
    queryFn: () => wesService.getRunLogs(runId),
    enabled: !!runId,
    ...options,
  });
};

// Fetch Log Content
export const useLogContent = (logUrl: string, options?: UseQueryOptions<string>) => {
  return useQuery<string>({
    queryKey: queryKeys.logContent(logUrl),
    queryFn: () => wesService.fetchLogContent(logUrl),
    enabled: !!logUrl,
    ...options,
  });
};

// Submit Run
export const useSubmitRun = (options?: UseMutationOptions<RunResponse, Error, WorkflowSubmission>) => {
  const queryClient = useQueryClient();
  
  return useMutation<RunResponse, Error, WorkflowSubmission>({
    mutationFn: (workflow) => wesService.submitRun(workflow),
    onSuccess: () => {
      // Invalidate runs list to refresh after submission
      queryClient.invalidateQueries({ queryKey: [queryKeys.runs] });
    },
    ...options,
  });
};

// Cancel Run
export const useCancelRun = (options?: UseMutationOptions<RunResponse, Error, string>) => {
  const queryClient = useQueryClient();
  
  return useMutation<RunResponse, Error, string>({
    mutationFn: (runId) => wesService.cancelRun(runId),
    onSuccess: (data, runId) => {
      // Invalidate specific run queries
      queryClient.invalidateQueries({ queryKey: queryKeys.run(runId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.runStatus(runId) });
      queryClient.invalidateQueries({ queryKey: [queryKeys.runs] });
    },
    ...options,
  });
};
