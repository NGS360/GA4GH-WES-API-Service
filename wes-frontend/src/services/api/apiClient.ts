import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse, AxiosError } from 'axios';
import { getAuthToken, refreshToken } from '../auth/authService';

class ApiClient {
  private client: AxiosInstance;
  private baseURL: string;
  private useProxy: boolean;

  constructor(baseURL: string, useProxy: boolean = true) {
    this.baseURL = baseURL;
    this.useProxy = useProxy;
    
    this.client = axios.create({
      baseURL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.setupInterceptors();
  }

  private setupInterceptors(): void {
    // Request interceptor - add auth token if not using proxy
    this.client.interceptors.request.use(
      (config) => {
        // If we're not using the proxy, add the auth token
        // The proxy handles authentication on its own
        if (!this.useProxy) {
          const token = getAuthToken();
          if (token) {
            config.headers.Authorization = `Bearer ${token}`;
          }
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Response interceptor - handle errors and token refresh
    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean };
        
        // Handle 401 Unauthorized - token expired
        if (error.response?.status === 401 && !originalRequest._retry && !this.useProxy) {
          originalRequest._retry = true;
          try {
            await refreshToken();
            const token = getAuthToken();
            this.client.defaults.headers.common.Authorization = `Bearer ${token}`;
            return this.client(originalRequest);
          } catch (refreshError) {
            // Redirect to login if refresh fails
            window.location.href = '/auth/login';
            return Promise.reject(refreshError);
          }
        }
        
        return Promise.reject(error);
      }
    );
  }

  // Helper method to determine if we should use the proxy
  private getUrl(url: string): string {
    if (this.useProxy) {
      // For proxy requests, we need to use the /api/proxy endpoint
      // and pass the original endpoint as a query parameter
      return `/api/proxy?endpoint=${encodeURIComponent(url.startsWith('/') ? url.substring(1) : url)}`;
    }
    return url;
  }

  async get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const finalUrl = this.getUrl(url);
    const response: AxiosResponse<T> = await this.client.get(finalUrl, config);
    return response.data;
  }

  async post<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    const finalUrl = this.getUrl(url);
    const response: AxiosResponse<T> = await this.client.post(finalUrl, data, config);
    return response.data;
  }

  async put<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    const finalUrl = this.getUrl(url);
    const response: AxiosResponse<T> = await this.client.put(finalUrl, data, config);
    return response.data;
  }

  async delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const finalUrl = this.getUrl(url);
    const response: AxiosResponse<T> = await this.client.delete(finalUrl, config);
    return response.data;
  }
}

export default ApiClient;
