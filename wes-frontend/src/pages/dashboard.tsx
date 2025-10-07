import { useState } from 'react';
import {
  Grid,
  Paper,
  Typography,
  Box,
  Card,
  CardContent,
  CircularProgress,
} from '@mui/material';
import Layout from '../components/common/Layout';
import { useServiceInfo, useRunsList } from '../hooks/useWesApi';
import { RunState } from '../types/wes';
import RecentRunsList from '../components/dashboard/RecentRunsList';
import StatusChart from '../components/dashboard/StatusChart';

export default function Dashboard() {
  const { data: serviceInfo, isLoading: isLoadingServiceInfo } = useServiceInfo();
  const { data: runsData, isLoading: isLoadingRuns } = useRunsList({
    page_size: 5,
  });

  // Calculate counts
  const counts = {
    total: runsData?.runs.length || 0,
    running: runsData?.runs.filter(run => run.state === RunState.RUNNING).length || 0,
    completed: runsData?.runs.filter(run => run.state === RunState.COMPLETE).length || 0,
    failed: runsData?.runs.filter(run => 
      run.state === RunState.EXECUTOR_ERROR || run.state === RunState.SYSTEM_ERROR
    ).length || 0,
  };

  return (
    <Layout title="Dashboard">
      <Grid container spacing={3}>
        {/* Stats Summary */}
        <Grid item xs={12}>
          <Typography variant="h4" gutterBottom>
            Workflow Execution Dashboard
          </Typography>
        </Grid>

        {/* Stats Cards */}
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Total Runs
              </Typography>
              <Typography variant="h3">
                {isLoadingRuns ? <CircularProgress size={24} /> : counts.total}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Running
              </Typography>
              <Typography variant="h3" color="primary">
                {isLoadingRuns ? <CircularProgress size={24} /> : counts.running}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Completed
              </Typography>
              <Typography variant="h3" color="success.main">
                {isLoadingRuns ? <CircularProgress size={24} /> : counts.completed}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Failed
              </Typography>
              <Typography variant="h3" color="error">
                {isLoadingRuns ? <CircularProgress size={24} /> : counts.failed}
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* Status Chart */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Run Status Distribution
            </Typography>
            <Box height={300}>
              <StatusChart runs={runsData?.runs || []} />
            </Box>
          </Paper>
        </Grid>

        {/* Recent Runs */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Recent Workflow Runs
            </Typography>
            <RecentRunsList runs={runsData?.runs || []} isLoading={isLoadingRuns} />
          </Paper>
        </Grid>

        {/* Service Info */}
        <Grid item xs={12}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Service Information
            </Typography>
            {isLoadingServiceInfo ? (
              <CircularProgress />
            ) : (
              <Box>
                <Typography>
                  <strong>Supported Workflow Types:</strong>{' '}
                  {serviceInfo?.workflow_type_versions
                    ? Object.keys(serviceInfo.workflow_type_versions).join(', ')
                    : 'N/A'}
                </Typography>
                <Typography>
                  <strong>Supported WES Versions:</strong>{' '}
                  {serviceInfo?.supported_wes_versions?.join(', ') || 'N/A'}
                </Typography>
                <Typography>
                  <strong>Supported Filesystem Protocols:</strong>{' '}
                  {serviceInfo?.supported_filesystem_protocols?.join(', ') || 'N/A'}
                </Typography>
              </Box>
            )}
          </Paper>
        </Grid>
      </Grid>
    </Layout>
  );
}
