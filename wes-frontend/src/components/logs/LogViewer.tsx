import { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Paper,
  TextField,
  InputAdornment,
  Button,
  Tabs,
  Tab,
  CircularProgress,
} from '@mui/material';
import { Search as SearchIcon, Download as DownloadIcon } from '@mui/icons-material';
import { useLogContent } from '../../hooks/useWesApi';

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
      id={`log-tabpanel-${index}`}
      aria-labelledby={`log-tab-${index}`}
      {...other}
    >
      {value === index && <Box>{children}</Box>}
    </div>
  );
}

interface LogViewerProps {
  stdout?: string;
  stderr?: string;
  stdoutUrl?: string;
  stderrUrl?: string;
}

const LogViewer: React.FC<LogViewerProps> = ({
  stdout,
  stderr,
  stdoutUrl,
  stderrUrl,
}) => {
  const [activeTab, setActiveTab] = useState(0);
  const [searchTerm, setSearchTerm] = useState('');
  const [filteredStdout, setFilteredStdout] = useState<string[]>([]);
  const [filteredStderr, setFilteredStderr] = useState<string[]>([]);
  
  // Fetch log content if URL is provided
  const { data: stdoutContent, isLoading: isLoadingStdout } = useLogContent(stdoutUrl || '', {
    enabled: !!stdoutUrl,
  });
  
  const { data: stderrContent, isLoading: isLoadingStderr } = useLogContent(stderrUrl || '', {
    enabled: !!stderrUrl && activeTab === 1,
  });
  
  // Use either the fetched log content or the provided stdout/stderr
  const stdoutLog = stdoutContent || stdout || '';
  const stderrLog = stderrContent || stderr || '';
  
  // Filter logs based on search term
  useEffect(() => {
    if (stdoutLog) {
      const lines = stdoutLog.split('\n');
      if (!searchTerm) {
        setFilteredStdout(lines);
      } else {
        const filtered = lines.filter(line => 
          line.toLowerCase().includes(searchTerm.toLowerCase())
        );
        setFilteredStdout(filtered);
      }
    } else {
      setFilteredStdout([]);
    }
    
    if (stderrLog) {
      const lines = stderrLog.split('\n');
      if (!searchTerm) {
        setFilteredStderr(lines);
      } else {
        const filtered = lines.filter(line => 
          line.toLowerCase().includes(searchTerm.toLowerCase())
        );
        setFilteredStderr(filtered);
      }
    } else {
      setFilteredStderr([]);
    }
  }, [stdoutLog, stderrLog, searchTerm]);
  
  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue);
  };
  
  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(event.target.value);
  };
  
  const handleDownload = () => {
    const content = activeTab === 0 ? stdoutLog : stderrLog;
    const filename = activeTab === 0 ? 'stdout.log' : 'stderr.log';
    
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
          <Tab label="Standard Error" disabled={!stderr && !stderrUrl} />
        </Tabs>
        
        <Box display="flex" alignItems="center">
          <TextField
            size="small"
            placeholder="Search logs..."
            value={searchTerm}
            onChange={handleSearchChange}
            InputProps={{
              startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment>,
            }}
            sx={{ mr: 1 }}
          />
          <Button
            variant="outlined"
            startIcon={<DownloadIcon />}
            onClick={handleDownload}
            disabled={(activeTab === 0 && !stdoutLog) || (activeTab === 1 && !stderrLog)}
          >
            Download
          </Button>
        </Box>
      </Box>
      
      <TabPanel value={activeTab} index={0}>
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
          {isLoadingStdout ? (
            <Box display="flex" justifyContent="center" p={4}>
              <CircularProgress />
            </Box>
          ) : filteredStdout.length > 0 ? (
            filteredStdout.map((line, index) => (
              <div key={index}>{line}</div>
            ))
          ) : (
            <Typography variant="body2" color="text.secondary">No log output available</Typography>
          )}
        </Paper>
      </TabPanel>
      
      <TabPanel value={activeTab} index={1}>
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
          {isLoadingStderr ? (
            <Box display="flex" justifyContent="center" p={4}>
              <CircularProgress />
            </Box>
          ) : filteredStderr.length > 0 ? (
            filteredStderr.map((line, index) => (
              <div key={index}>{line}</div>
            ))
          ) : (
            <Typography variant="body2" color="text.secondary">No error output available</Typography>
          )}
        </Paper>
      </TabPanel>
    </Box>
  );
};

export default LogViewer;

