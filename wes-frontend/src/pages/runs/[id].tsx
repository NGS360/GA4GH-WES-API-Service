import { useState } from 'react';
import { useRouter } from 'next/router';
import {
  Box,
  Typography,
  Paper,
  Tabs,
  Tab,
  CircularProgress,
  Chip,
  Button,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Alert,
} from '@mui/material';
import Layout from '../../components/common/Layout';
import { useRun, useRunStatus, useCancelRun } from '../../hooks/useWesApi';
import { RunState } from '../../types/wes';
import LogViewer from '../../components/logs/LogViewer';
import { format } from 'date-fns';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`run-tabpanel-${index}`}
      aria-labelledby={`run-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ pt: 3 }}>{children}</Box>}
    </div>
  );
}

export default function RunDetailPage() {
  const router = useRouter();
  const { id } = router.query;
  const runId = id as string;
  
  const [activeTab, setActiveTab] = useState(0);
  
  // Get run details with 10-second polling for active runs
  const { data: run, isLoading: isLoadingRun, error } = useRun(runId);
  const { data: status } = useRunStatus(runId, { 
    pollInterval: run?.state === RunState.RUNNING || run?.state === RunState.QUEUED ? 10000 : 0,
  });
  
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
    return (
      <Layout title="Run Details">
        <Box display="flex" justifyContent="center" p={4}>
          <CircularProgress />
        </Box>
      </Layout>
    );
  }
  
  if (error || !run) {
    return (
      <Layout title="Run Details">
        <Alert severity="error">
          {error ? `Error loading run: ${(error as Error).message}` : 'Run not found'}
        </Alert>
      </Layout>
    );
  }
  
  const currentState = status?.state || run.state;
  const isActive = currentState === RunState.RUNNING || currentState === RunState.QUEUED;
  
  // Check if we have log information in the outputs
  const logInfo = run.outputs?.logs || {};
  const hasTaskLogs = run.task_logs && run.task_logs.length > 0;
  
  return (
    <Layout title={`Run: ${runId}`}>
      <Box mb={3}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h4" gutterBottom>
            Run Details
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
        
        <Paper sx={{ mb: 3 }}>
          <Tabs value={activeTab} onChange={handleTabChange}>
            <Tab label="Overview" />
            <Tab label="Tasks" />
            <Tab label="Logs" />
            <Tab label="Outputs" />
          </Tabs>
          
          <TabPanel value={activeTab} index={0}>
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader title="Workflow Information" />
                  <CardContent>
                    <Typography><strong>Run ID:</strong> {run.run_id}</Typography>
                    <Typography><strong>Type:</strong> {run.request.workflow_type}</Typography>
                    <Typography><strong>Version:</strong> {run.request.workflow_type_version}</Typography>
                    <Typography><strong>URL:</strong> {run.request.workflow_url}</Typography>
                    <Typography><strong>State:</strong> {currentState}</Typography>
                    <Typography>
                      <strong>Start Time:</strong> {run.run_log.start_time ? format(new Date(run.run_log.start_time), 'PPpp') : 'N/A'}
                    </Typography>
                    <Typography>
                      <strong>End Time:</strong> {run.run_log.end_time ? format(new Date(run.run_log.end_time), 'PPpp') : 'N/A'}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              
              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader title="Parameters" />
                  <CardContent>
                    <pre style={{ overflow: 'auto', maxHeight: '300px' }}>
                      {JSON.stringify(run.request.workflow_params, null, 2)}
                    </pre>
                  </CardContent>
                </Card>
              </Grid>
              
              {run.request.tags && Object.keys(run.request.tags).length > 0 && (
                <Grid item xs={12}>
                  <Card>
                    <CardHeader title="Tags" />
                    <CardContent>
                      <Box>
                        {Object.entries(run.request.tags).map(([key, value]) => (
                          <Chip key={key} label={`${key}: ${value}`} sx={{ mr: 1, mb: 1 }} />
                        ))}
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              )}
            </Grid>
          </TabPanel>
          
          <TabPanel value={activeTab} index={1}>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Task Name</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Start Time</TableCell>
                    <TableCell>End Time</TableCell>
                    <TableCell>Exit Code</TableCell>
                    <TableCell>Logs</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {hasTaskLogs ? (
                    run.task_logs.map((task) => (
                      <TableRow key={task.name}>
                        <TableCell>{task.name}</TableCell>
                        <TableCell>
                          {task.exit_code !== undefined ? (
                            <Chip 
                              label={task.exit_code === 0 ? 'Success' : 'Failed'} 
                              color={task.exit_code === 0 ? 'success' : 'error'} 
                            />
                          ) : (
                            <Chip label="Running" color="primary" />
                          )}
                        </TableCell>
                        <TableCell>{task.start_time ? format(new Date(task.start_time), 'PPpp') : 'N/A'}</TableCell>
                        <TableCell>{task.end_time ? format(new Date(task.end_time), 'PPpp') : 'N/A'}</TableCell>
                        <TableCell>{task.exit_code !== undefined ? task.exit_code : 'N/A'}</TableCell>
                        <TableCell>
                          {task.stdout_url && (
                            <Button variant="text" href={task.stdout_url} target="_blank" size="small">
                              stdout
                            </Button>
                          )}
                          {task.stderr_url && (
                            <Button variant="text" href={task.stderr_url} target="_blank" size="small">
                              stderr
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell colSpan={6} align="center">
                        {isActive ? 'No tasks available yet' : 'No tasks found for this run'}
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </TabPanel>
          
          <TabPanel value={activeTab} index={2}>
            <LogViewer 
              stdout={run.run_log.stdout}
              stderr={run.run_log.stderr}
              stdoutUrl={run.run_log.stdout_url || logInfo.run_log}
              stderrUrl={run.run_log.stderr_url}
            />
            
            {/* Show log URL from outputs if available */}
            {logInfo.run_log && !run.run_log.stdout_url && (
              <Box mt={3}>
                <Alert severity="info">
                  <Typography variant="body1">
                    <strong>CloudWatch Log:</strong>{' '}
                    <Button 
                      variant="contained" 
                      color="primary" 
                      href={logInfo.run_log} 
                      target="_blank"
                      size="small"
                      sx={{ ml: 1 }}
                    >
                      View in CloudWatch
                    </Button>
                  </Typography>
                </Alert>
              </Box>
            )}
          </TabPanel>
          
          <TabPanel value={activeTab} index={3}>
            <Card>
              <CardHeader title="Workflow Outputs" />
              <CardContent>
                <pre style={{ overflow: 'auto', maxHeight: '500px' }}>
                  {JSON.stringify(run.outputs, null, 2)}
                </pre>
              </CardContent>
            </Card>
          </TabPanel>
        </Paper>
      </Box>
    </Layout>
  );
}
