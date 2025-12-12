import axios from 'axios';

// Default to localhost:8001/api (alternate dev port)
const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001/api';

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
