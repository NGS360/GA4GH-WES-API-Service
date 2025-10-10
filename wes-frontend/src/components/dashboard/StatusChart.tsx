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
