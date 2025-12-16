# GA4GH WES Frontend Implementation Plan

This document outlines the step-by-step implementation plan for creating a React-based frontend for the GA4GH Workflow Execution Service (WES) API with AWS HealthOmics integration.

## Phase 1: Project Setup and Foundation

### 1.1 Initialize Next.js Project

```bash
# Create a new Next.js project with TypeScript
npx create-next-app@latest wes-frontend --typescript --eslint --tailwind --app

# Navigate to project directory
cd wes-frontend

# Install core dependencies
npm install @mui/material @mui/icons-material @emotion/react @emotion/styled
npm install react-query axios date-fns
npm install next-auth
```

### 1.2 Configure Project Structure

Create the directory structure as outlined in the architecture document:

```bash
# Create directory structure
mkdir -p src/{components,hooks,services,types,utils}/{common,dashboard,runs,submission,logs}
mkdir -p src/pages/api/{auth,proxy}
```

### 1.3 Set Up Environment Configuration

Create environment configuration files:

```bash
# Create .env.local file
touch .env.local
```

Add the following to `.env.local`:

```
NEXT_PUBLIC_WES_API_URL=http://localhost:8080
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=your-secret-key-here
```

### 1.4 Configure TypeScript

Update `tsconfig.json` with appropriate settings:

```json
{
  "compilerOptions": {
    "target": "es5",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "node",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx"],
  "exclude": ["node_modules"]
}
```

### 1.5 Set Up Material UI Theme

Create a custom theme file:

```tsx
// src/styles/theme.ts
import { createTheme } from '@mui/material/styles';

const theme = createTheme({
  palette: {
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
    background: {
      default: '#f5f5f5',
    },
  },
  typography: {
    fontFamily: [
      '-apple-system',
      'BlinkMacSystemFont',
      '"Segoe UI"',
      'Roboto',
      '"Helvetica Neue"',
      'Arial',
      'sans-serif',
    ].join(','),
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
        },
      },
    },
  },
});

export default theme;
```

### 1.6 Configure React Query

Set up React Query provider:

```tsx
// src/pages/_app.tsx
import { AppProps } from 'next/app';
import { ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { QueryClient, QueryClientProvider } from 'react-query';
import { ReactQueryDevtools } from 'react-query/devtools';
import { SessionProvider } from 'next-auth/react';
import theme from '../styles/theme';

// Create a client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function MyApp({ Component, pageProps: { session, ...pageProps } }: AppProps) {
  return (
    <SessionProvider session={session}>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider theme={theme}>
          <CssBaseline />
          <Component {...pageProps} />
        </ThemeProvider>
        <ReactQueryDevtools initialIsOpen={false} />
      </QueryClientProvider>
    </SessionProvider>
  );
}

export default MyApp;
```

## Phase 2: Authentication Implementation

### 2.1 Set Up NextAuth.js

Configure NextAuth.js for authentication:

```tsx
// src/pages/api/auth/[...nextauth].ts
import NextAuth from 'next-auth';
import CredentialsProvider from 'next-auth/providers/credentials';

export default NextAuth({
  providers: [
    CredentialsProvider({
      name: 'Credentials',
      credentials: {
        username: { label: 'Username', type: 'text' },
        password: { label: 'Password', type: 'password' },
      },
      async authorize(credentials) {
        // This is where you would validate credentials against your backend
        // For now, we'll use a simple check
        if (
          credentials?.username === 'admin' &&
          credentials?.password === 'password'
        ) {
          return {
            id: '1',
            name: 'Admin User',
            email: 'admin@example.com',
          };
        }
        return null;
      },
    }),
  ],
  session: {
    strategy: 'jwt',
    maxAge: 30 * 24 * 60 * 60, // 30 days
  },
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        token.id = user.id;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.id = token.id as string;
      }
      return session;
    },
  },
  pages: {
    signIn: '/auth/login',
    error: '/auth/error',
  },
});
```

### 2.2 Create Login Page

Create a login page:

```tsx
// src/pages/auth/login.tsx
import { useState } from 'react';
import { signIn } from 'next-auth/react';
import { useRouter } from 'next/router';
import {
  Box,
  Button,
  TextField,
  Typography,
  Container,
  Paper,
  Alert,
} from '@mui/material';

export default function Login() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    const result = await signIn('credentials', {
      redirect: false,
      username,
      password,
    });

    setIsLoading(false);

    if (result?.error) {
      setError('Invalid username or password');
    } else {
      router.push('/dashboard');
    }
  };

  return (
    <Container maxWidth="sm">
      <Box sx={{ mt: 8 }}>
        <Paper sx={{ p: 4 }}>
          <Typography variant="h4" component="h1" gutterBottom align="center">
            GA4GH WES Portal
          </Typography>
          <Typography variant="h6" gutterBottom align="center">
            Sign In
          </Typography>

          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}

          <Box component="form" onSubmit={handleSubmit} noValidate>
            <TextField
              margin="normal"
              required
              fullWidth
              id="username"
              label="Username"
              name="username"
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
            <TextField
              margin="normal"
              required
              fullWidth
              name="password"
              label="Password"
              type="password"
              id="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Button
              type="submit"
              fullWidth
              variant="contained"
              sx={{ mt: 3, mb: 2 }}
              disabled={isLoading}
            >
              {isLoading ? 'Signing in...' : 'Sign In'}
            </Button>
          </Box>
        </Paper>
      </Box>
    </Container>
  );
}
```

### 2.3 Create Auth Guard Component

Create an authentication guard component:

```tsx
// src/components/common/AuthGuard.tsx
import { useEffect, useState } from 'react';
import { useSession } from 'next-auth/react';
import { useRouter } from 'next/router';
import { CircularProgress, Box } from '@mui/material';

interface AuthGuardProps {
  children: React.ReactNode;
}

const AuthGuard: React.FC<AuthGuardProps> = ({ children }) => {
  const { data: session, status } = useSession();
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (status === 'loading') {
      return;
    }

    if (!session) {
      router.push('/auth/login');
    } else {
      setIsLoading(false);
    }
  }, [session, status, router]);

  if (isLoading) {
    return (
      <Box
        display="flex"
        justifyContent="center"
        alignItems="center"
        minHeight="100vh"
      >
        <CircularProgress />
      </Box>
    );
  }

  return <>{children}</>;
};

export default AuthGuard;
```

## Phase 3: Layout and Navigation

### 3.1 Create Layout Component

Create a layout component:

```tsx
// src/components/common/Layout.tsx
import { useState } from 'react';
import { useSession, signOut } from 'next-auth/react';
import {
  AppBar,
  Box,
  CssBaseline,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
  Typography,
  Button,
  Avatar,
  Menu,
  MenuItem,
} from '@mui/material';
import {
  Menu as MenuIcon,
  Dashboard as DashboardIcon,
  List as ListIcon,
  Add as AddIcon,
  AccountCircle,
} from '@mui/icons-material';
import Link from 'next/link';
import { useRouter } from 'next/router';

const drawerWidth = 240;

interface LayoutProps {
  children: React.ReactNode;
  title?: string;
}

export default function Layout({ children, title = 'GA4GH WES Portal' }: LayoutProps) {
  const { data: session } = useSession();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  const handleMenu = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
  };

  const handleLogout = async () => {
    handleClose();
    await signOut({ redirect: false });
    router.push('/auth/login');
  };

  const drawer = (
    <div>
      <Toolbar>
        <Typography variant="h6" noWrap component="div">
          WES Portal
        </Typography>
      </Toolbar>
      <Divider />
      <List>
        <ListItem disablePadding>
          <ListItemButton component={Link} href="/dashboard">
            <ListItemIcon>
              <DashboardIcon />
            </ListItemIcon>
            <ListItemText primary="Dashboard" />
          </ListItemButton>
        </ListItem>
        <ListItem disablePadding>
          <ListItemButton component={Link} href="/runs">
            <ListItemIcon>
              <ListIcon />
            </ListItemIcon>
            <ListItemText primary="Workflow Runs" />
          </ListItemButton>
        </ListItem>
        <ListItem disablePadding>
          <ListItemButton component={Link} href="/submit">
            <ListItemIcon>
              <AddIcon />
            </ListItemIcon>
            <ListItemText primary="Submit Workflow" />
          </ListItemButton>
        </ListItem>
      </List>
    </div>
  );

  return (
    <Box sx={{ display: 'flex' }}>
      <CssBaseline />
      <AppBar
        position="fixed"
        sx={{
          width: { sm: `calc(100% - ${drawerWidth}px)` },
          ml: { sm: `${drawerWidth}px` },
        }}
      >
        <Toolbar>
          <IconButton
            color="inherit"
            aria-label="open drawer"
            edge="start"
            onClick={handleDrawerToggle}
            sx={{ mr: 2, display: { sm: 'none' } }}
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1 }}>
            {title}
          </Typography>
          {session && (
            <div>
              <IconButton
                size="large"
                aria-label="account of current user"
                aria-controls="menu-appbar"
                aria-haspopup="true"
                onClick={handleMenu}
                color="inherit"
              >
                <Avatar sx={{ width: 32, height: 32 }}>
                  {session.user?.name?.charAt(0) || 'U'}
                </Avatar>
              </IconButton>
              <Menu
                id="menu-appbar"
                anchorEl={anchorEl}
                anchorOrigin={{
                  vertical: 'bottom',
                  horizontal: 'right',
                }}
                keepMounted
                transformOrigin={{
                  vertical: 'top',
                  horizontal: 'right',
                }}
                open={Boolean(anchorEl)}
                onClose={handleClose}
              >
                <MenuItem disabled>
                  {session.user?.name || 'User'}
                </MenuItem>
                <Divider />
                <MenuItem onClick={handleLogout}>Logout</MenuItem>
              </Menu>
            </div>
          )}
        </Toolbar>
      </AppBar>
      <Box
        component="nav"
        sx={{ width: { sm: drawerWidth }, flexShrink: { sm: 0 } }}
      >
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={handleDrawerToggle}
          ModalProps={{
            keepMounted: true, // Better open performance on mobile.
          }}
          sx={{
            display: { xs: 'block', sm: 'none' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth },
          }}
        >
          {drawer}
        </Drawer>
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', sm: 'block' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth },
          }}
          open
        >
          {drawer}
        </Drawer>
      </Box>
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: 3,
          width: { sm: `calc(100% - ${drawerWidth}px)` },
          mt: '64px',
        }}
      >
        {children}
      </Box>
    </Box>
  );
}
```

### 3.2 Create Home Page

Create a home page that redirects to the dashboard:

```tsx
// src/pages/index.tsx
import { useEffect } from 'react';
import { useRouter } from 'next/router';
import { CircularProgress, Box } from '@mui/material';

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    router.push('/dashboard');
  }, [router]);

  return (
    <Box
      display="flex"
      justifyContent="center"
      alignItems="center"
      minHeight="100vh"
    >
      <CircularProgress />
    </Box>
  );
}
```

## Phase 4: Dashboard Implementation

### 4.1 Create Dashboard Page

Create the dashboard page:

```tsx
// src/pages/dashboard.tsx
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
import AuthGuard from '../components/common/AuthGuard';
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
    <AuthGuard>
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
                      : 'None'}
                  </Typography>
                  <Typography>
                    <strong>WES API Version:</strong>{' '}
                    {serviceInfo?.supported_wes_versions?.join(', ') || 'Unknown'}
                  </Typography>
                </Box>
              )}
            </Paper>
          </Grid>
        </Grid>
      </Layout>
    </AuthGuard>
  );
}
```

### 4.2 Create Dashboard Components

Create the status chart component:

```tsx
// src/components/dashboard/StatusChart.tsx
import { useEffect, useState } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';
import { RunState } from '../../types/wes';
import { RunListItem } from '../../types/wes';

interface StatusChartProps {
  runs: RunListItem[];
}

interface ChartData {
  name: string;
  value: number;
  color: string;
}

const COLORS = {
  [RunState.COMPLETE]: '#4caf50',
  [RunState.RUNNING]: '#2196f3',
  [RunState.QUEUED]: '#ff9800',
  [RunState.INITIALIZING]: '#9c27b0',
  [RunState.EXECUTOR_ERROR]: '#f44336',
  [RunState.SYSTEM_ERROR]: '#d32f2f',
  [RunState.CANCELED]: '#757575',
  [RunState.CANCELING]: '#bdbdbd',
  [RunState.PAUSED]: '#607d8b',
  [RunState.UNKNOWN]: '#9e9e9e',
};

const StatusChart: React.FC<StatusChartProps> = ({ runs }) => {
  const [chartData, setChartData] = useState<ChartData[]>([]);

  useEffect(() => {
    if (!runs.length) return;

    // Count runs by state
    const counts: Record<string, number> = {};
    runs.forEach((run) => {
      counts[run.state] = (counts[run.state] || 0) + 1;
    });

    // Convert to chart data
    const data: ChartData[] = Object.entries(counts).map(([state, count]) => ({
      name: state,
      value: count,
      color: COLORS[state as RunState] || '#9e9e9e',
    }));

    setChartData(data);
  }, [runs]);

  if (!chartData.length) {
    return <div>No data available</div>;
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <PieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="50%"
          labelLine={false}
          outerRadius={80}
          fill="#8884d8"
          dataKey="value"
          label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
        >
          {chartData.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={entry.color} />
          ))}
        </Pie>
        <Tooltip />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  );
};

export default StatusChart;
```

Create the recent runs list component:

```tsx
// src/components/dashboard/RecentRunsList.tsx
import {
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  Chip,
  IconButton,
  CircularProgress,
  Divider,
} from '@mui/material';
import { Visibility as VisibilityIcon } from '@mui/icons-material';
import { RunState, RunListItem } from '../../types/wes';
import Link from 'next/link';
import { format } from 'date-fns';

interface RecentRunsListProps {
  runs: RunListItem[];
  isLoading: boolean;
}

const RecentRunsList: React.FC<RecentRunsListProps> = ({ runs, isLoading }) => {
  if (isLoading) {
    return <CircularProgress />;
  }

  if (!runs.length) {
    return <div>No recent runs</div>;
  }

  return (
    <List>
      {runs.map((run, index) => (
        <div key={run.run_id}>
          <ListItem>
            <ListItemText
              primary={run.run_id}
              secondary={`Updated: ${format(new Date(), 'PPpp')}`}
            />
            <ListItemSecondaryAction>
              <Chip
                label={run.state}
                color={
                  run.state === RunState.COMPLETE
                    ? 'success'
                    : run.state === RunState.RUNNING
                    ? 'primary'
                    : run.state === RunState.QUEUED
                    ? 'warning'
                    : run.state.includes('ERROR')
                    ? 'error'
                    : 'default'
                }
                size="small"
                sx={{ mr: 1 }}
              />
              <IconButton
                edge="end"
                aria-label="view"
                component={Link}
                href={`/runs/${run.run_id}`}
              >
                <VisibilityIcon />
              </IconButton>
            </ListItemSecondaryAction>
          </ListItem>
          {index < runs.length - 1 && <Divider />}
        </div>
      ))}
    </List>
  );
};

export default RecentRunsList;
```

## Phase 5: Workflow Runs List Implementation

### 5.1 Create Runs List Page

Create the runs list page:

```tsx
// src/pages/runs/index.tsx
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
} from '@mui/material';
import { Search as SearchIcon, Refresh as RefreshIcon } from '@mui/icons-material';
import Layout from '../../components/common/Layout';
import AuthGuard from '../../components/common/AuthGuard';
import RunsList from '../../components/runs/RunsList';
import { useRunsList } from '../../hooks/useWesApi';
import { RunState, RunListParams } from '../../types/wes';

export default function RunsPage() {
  const [filters, setFilters] = useState<RunListParams>({
    page_size: 10,
  });
  const [searchTerm, setSearchTerm] = useState('');
  
  const { data, isLoading, refetch } = useRunsList(filters);
  
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
  
  return (
    <AuthGuard>
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
            <RunsList runs={data?.runs || []} />
          )}
        </Box>
      </Layout