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
              primary={run.name || 'Unnamed workflow'}
              secondary={`ID: ${run.run_id} • Updated: ${format(new Date(), 'PPpp')}`}
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
