import { apiClient } from '../client';
import { actionsService } from './actionsService';

export interface Catalog {
    name: string;
    description?: string;
    created?: string;
}

// Use Actions service if enabled, otherwise direct API
const useActions = () => actionsService.isEnabled();

export const catalogService = {
    getCatalogs: async (): Promise<Catalog[]> => {
        if (useActions()) {
            return actionsService.getCatalogs();
        }
        const response = await apiClient.get<Catalog[]>('/catalogs');
        return response.data;
    },

    getCatalogMetadata: async (catalogName: string): Promise<any> => {
        const response = await apiClient.get(`/catalogs/${catalogName}`);
        return response.data;
    },

    getApartados: async (catalogName: string): Promise<any[]> => {
        if (useActions()) {
            return actionsService.getApartados(catalogName);
        }
        const response = await apiClient.get(`/catalogs/${catalogName}/apartados`);
        return response.data;
    },

    getVariables: async (catalogName: string, apartados?: string[]): Promise<any[]> => {
        if (useActions()) {
            return actionsService.getVariables(catalogName, apartados);
        }
        const params = new URLSearchParams();
        if (apartados && apartados.length > 0) {
            params.append('apartados', apartados.join(','));
        }
        const response = await apiClient.get(`/catalogs/${catalogName}/variables`, { params });
        return response.data;
    },

    getDimensions: async (catalogName: string): Promise<any[]> => {
        if (useActions()) {
            return actionsService.getDimensions(catalogName);
        }
        const response = await apiClient.get(`/catalogs/${catalogName}/dimensions`);
        return response.data;
    },

    getMembers: async (catalogName: string, dimension: string, hierarchy: string, level: string): Promise<any[]> => {
        if (useActions()) {
            return actionsService.getMembers(catalogName, dimension, hierarchy, level);
        }
        const response = await apiClient.get(`/catalogs/${catalogName}/members`, {
            params: { dimension, hierarchy, level }
        });
        return response.data;
    },

    executeQuery: async (payload: any): Promise<any> => {
        if (useActions()) {
            return actionsService.executeQuery(payload);
        }
        const response = await apiClient.post('/query/execute', payload);
        return response.data;
    },
};

