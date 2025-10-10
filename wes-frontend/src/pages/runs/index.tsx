import { useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  TextField,
  InputAdornment,
  Grid,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  Chip,
  IconButton,
} from '@mui/material';
import { Search as SearchIcon, Refresh as RefreshIcon, Visibility as VisibilityIcon } from '@mui/icons-material';
import Layout from '../../components/common/Layout';
import { useRunsList, useCancelRun } from '../../hooks/useWesApi';
import { RunState, RunListParams } from '../../types/wes';
import Link from 'next/link';
import { format } from 'date-fns';

export default function RunsPage() {
  const [filters, setFilters] = useState<RunListParams>({
    page_size: 10,
  });
  const [searchTerm, setSearchTerm] = useState('');
  
  const { data, isLoading, refetch } = useRunsList(filters);
  const { mutate: cancelRun, isLoading: isCancelling } = useCancelRun();
  
  const handleFilterChange = (field: keyof RunListParams, value: any) => {
    setFilters((prev) => ({
      ...prev,
      [field]: value,
    }));
  };
  
  const handleSearch = () => {
    // For now, we'll just use the tag field for searching
    handleFilterChange('tag', searchTerm);
  };
  
  const handleRefresh = () => {
    refetch();
  };

  const handleCancelRun = (runId: string) => {
    if (confirm('Are you sure you want to cancel this run?')) {
      cancelRun(runId);
    }
  };
  
  return (
    <Layout title="Workflow Runs">
      <Box mb={3}>
        <Typography variant="h4" gutterBottom>
          Workflow Runs
        </Typography>
        
        <Paper sx={{ p: 2, mb: 3 }}>
          <Grid container spacing={2} alignItems="flex-end">
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                label="Search"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <SearchIcon />
                    </InputAdornment>
                  ),
                }}
                onKeyPress={(e) => {
                  if (e.key === 'Enter') {
                    handleSearch();
                  }
                }}
              />
            </Grid>
            <Grid item xs={12} md={3}>
              <FormControl fullWidth>
                <InputLabel>Status</InputLabel>
                <Select
                  value={filters.state || ''}
                  onChange={(e) => handleFilterChange('state', e.target.value)}
                  label="Status"
                >
                  <MenuItem value="">All</MenuItem>
                  <MenuItem value={RunState.RUNNING}>Running</MenuItem>
                  <MenuItem value={RunState.COMPLETE}>Complete</MenuItem>
                  <MenuItem value={RunState.EXECUTOR_ERROR}>Failed</MenuItem>
                  <MenuItem value={RunState.QUEUED}>Queued</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={3}>
              <FormControl fullWidth>
                <InputLabel>Workflow Type</InputLabel>
                <Select
                  value={filters.workflow_type || ''}
                  onChange={(e) => handleFilterChange('workflow_type', e.target.value)}
                  label="Workflow Type"
                >
                  <MenuItem value="">All</MenuItem>
                  <MenuItem value="CWL">CWL</MenuItem>
                  <MenuItem value="WDL">WDL</MenuItem>
                  <MenuItem value="NFL">Nextflow</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={2}>
              <Button
                fullWidth
                variant="contained"
                startIcon={<RefreshIcon />}
                onClick={handleRefresh}
                disabled={isLoading}
              >
                Refresh
              </Button>
            </Grid>
          </Grid>
        </Paper>
        
        {isLoading ? (
          <Box display="flex" justifyContent="center" p={4}>
            <CircularProgress />
          </Box>
        ) : (
          <Paper>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Run ID</TableCell>
                    <TableCell>Name</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Start Time</TableCell>
                    <TableCell>End Time</TableCell>
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
                        {run.name || 'Unnamed workflow'}
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
                      <TableCell>{run.start_time ? format(new Date(run.start_time), 'PPpp') : 'N/A'}</TableCell>
                      <TableCell>{run.end_time ? format(new Date(run.end_time), 'PPpp') : 'N/A'}</TableCell>
                      <TableCell>
                        <IconButton component={Link} href={`/runs/${run.run_id}`}>
                          <VisibilityIcon />
                        </IconButton>
                        {(run.state === RunState.RUNNING || run.state === RunState.QUEUED) && (
                          <Button 
                            variant="outlined" 
                            color="error" 
                            size="small"
                            onClick={() => handleCancelRun(run.run_id)}
                            disabled={isCancelling}
                          >
                            Cancel
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            <TablePagination
              component="div"
              count={-1} // Unknown total count from API
              rowsPerPage={filters.page_size || 10}
              page={filters.page_token ? 1 : 0} // Simplified pagination
              onPageChange={(event, newPage) => {
                setFilters(prev => ({
                  ...prev,
                  page_token: newPage > 0 && data?.next_page_token ? data.next_page_token : '',
                }));
              }}
              onRowsPerPageChange={(event) => {
                setFilters(prev => ({
                  ...prev,
                  page_size: parseInt(event.target.value, 10),
                  page_token: '',
                }));
              }}
              rowsPerPageOptions={[5, 10, 25, 50]}
            />
          </Paper>
        )}
      </Box>
    </Layout>
  );
}
