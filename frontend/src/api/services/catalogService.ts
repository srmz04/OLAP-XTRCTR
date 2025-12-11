import { apiClient } from '../client';

export interface Catalog {
    name: string;
    description?: string;
    created?: string;
    // Add other fields as returned by the backend
}

export const catalogService = {
    /**
     * Fetch all available catalogs
     */
    getCatalogs: async (): Promise<Catalog[]> => {
        const response = await apiClient.get<Catalog[]>('/catalogs');
        return response.data;
    },

    /**
     * Fetch detailed metadata for a specific catalog
     */
    getMetadata: async (catalogName: string) => {
        const response = await apiClient.get(`/catalogs/${catalogName}`);
        return response.data;
    },
};
