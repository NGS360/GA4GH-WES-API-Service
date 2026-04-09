import type { NextApiRequest, NextApiResponse } from 'next';
import axios from 'axios';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  try {
    const apiUrl = process.env.NEXT_PUBLIC_WES_API_URL;
    const endpoint = req.query.endpoint as string;
    
    if (!endpoint) {
      return res.status(400).json({ error: 'Endpoint parameter is required' });
    }
    
    // Basic auth credentials (only used when backend has auth enabled)
    const username = process.env.WES_API_USERNAME || '';
    const password = process.env.WES_API_PASSWORD || '';
    
    // Handle query parameters
    const queryParams = { ...req.query };
    delete queryParams.endpoint; // Remove the endpoint parameter
    
    // Construct the full URL
    const url = `${apiUrl}/${endpoint}`;
    
    console.log(`Proxying request to: ${url}`);
    
    const axiosConfig: any = {
      method: req.method || 'GET',
      url: url,
      params: Object.keys(queryParams).length > 0 ? queryParams : undefined,
      data: req.body,
      headers: {
        'Content-Type': 'application/json',
      },
    };

    // Only add auth if credentials are configured
    if (username && password) {
      axiosConfig.auth = { username, password };
    }
    
    const response = await axios(axiosConfig);
    
    res.status(response.status).json(response.data);
  } catch (error: any) {
    console.error('API proxy error:', error);
    
    // Forward the error status if available
    const status = error.response?.status || 500;
    const errorMessage = error.response?.data?.detail || error.message || 'Failed to fetch data from API';
    
    res.status(status).json({ 
      error: errorMessage,
      path: error.response?.config?.url || 'unknown',
      method: error.response?.config?.method || 'unknown'
    });
  }
}
