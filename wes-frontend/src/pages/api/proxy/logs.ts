import type { NextApiRequest, NextApiResponse } from 'next';
import axios from 'axios';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  const { url } = req.query;
  
  if (!url || typeof url !== 'string') {
    return res.status(400).json({ error: 'URL parameter is required' });
  }

  try {
    // For CloudWatch logs, we need to use AWS SDK or a special endpoint
    if (url.includes('cloudwatch')) {
      // This is a simplified example - in a real app, you'd use AWS SDK
      // to fetch CloudWatch logs using the log group and stream from the URL
      const logGroupMatch = url.match(/log-group\/([^\/]+)/);
      const logStreamMatch = url.match(/log-events\/([^\/]+)/);
      
      if (!logGroupMatch || !logStreamMatch) {
        return res.status(400).json({ error: 'Invalid CloudWatch URL format' });
      }
      
      const logGroup = decodeURIComponent(logGroupMatch[1]);
      const logStream = decodeURIComponent(logStreamMatch[1]);
      
      // Here you would use AWS SDK to fetch logs
      // For this example, we'll just return a placeholder
      return res.status(200).send(`Logs for ${logGroup}/${logStream}`);
    } 
    
    // For direct URLs (like S3)
    const response = await axios.get(url, { responseType: 'text' });
    return res.status(200).send(response.data);
  } catch (error) {
    console.error('Error fetching logs:', error);
    return res.status(500).json({ error: 'Failed to fetch logs' });
  }
}
