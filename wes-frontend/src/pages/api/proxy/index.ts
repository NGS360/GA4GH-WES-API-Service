import type { NextApiRequest, NextApiResponse } from 'next';
import axios from 'axios';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  try {
    const apiUrl = process.env.NEXT_PUBLIC_WES_API_URL;
    const endpoint = req.query.endpoint as string;
    
    if (!endpoint) {
      return res.status(400).json({ error: 'Endpoint parameter is required' });
    }
    
    // Basic auth credentials (hardcoded for development)
    const username = 'admin'; // Replace with your username
    const password = 'password'; // Replace with your password
    
    const response = await axios({
      method: req.method || 'GET',
      url: `${apiUrl}/${endpoint}`,
      data: req.body,
      headers: {
        'Content-Type': 'application/json',
      },
      auth: {
        username,
        password,
      },
    });
    
    res.status(response.status).json(response.data);
  } catch (error: any) {
    console.error('API proxy error:', error);
    
    // Forward the error status if available
    const status = error.response?.status || 500;
    const errorMessage = error.response?.data?.detail || 'Failed to fetch data from API';
    
    res.status(status).json({ error: errorMessage });
  }
}

