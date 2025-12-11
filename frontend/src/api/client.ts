import axios from 'axios';

// Default to localhost:8001 if VITE_API_URL is not set
const BASE_URL = 'http://192.168.1.5:8000';

export const apiClient = axios.create({
    baseURL: BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Add response interceptor for global error handling
apiClient.interceptors.response.use(
    (response) => response,
    (error) => {
        // Log error or handle global states (e.g. auth redirect) here
        console.error('API Error:', error);
        return Promise.reject(error);
    }
);
