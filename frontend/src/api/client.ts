/**
 * API Client for DGIS OLAP Backend
 * Handles all HTTP requests to FastAPI server
 */

import axios from 'axios';

const BASE_URL = 'http://10.151.64.152:8000';

const api = axios.create({
    baseURL: BASE_URL,
    timeout: 30000,
    headers: {
        'Content-Type': 'application/json',
    },
});

export interface Catalog {
    name: string;
    description: string;
    created: string;
}

export interface Measure {
    id: string;
    name: string;
    caption: string;
    aggregator: string;
    type: 'measure';
}

export interface Level {
    name: string;
    depth: number;
    uniqueName: string;
    memberCount: number | null;
}

export interface Dimension {
    dimension: string;
    hierarchy: string;
    displayName: string;
    levels: Level[];
    type: 'dimension';
}

export interface Member {
    caption: string;
    uniqueName: string;
}

export interface QueryRequest {
    catalog: string;
    measures: Array<{ uniqueName: string }>;
    rows: Array<{
        dimension: string;
        hierarchy: string;
        level: string;
        depth?: number;
        members?: string[];
    }>;
    filters: Array<{
        dimension: string;
        hierarchy: string;
        members: string[];
    }>;
}

export interface QueryResponse {
    rows: Record<string, any>[];
    columns: Array<{
        field: string;
        headerName: string;
        sortable: boolean;
        filter: boolean;
    }>;
    rowCount: number;
}

export const olapApi = {
    // Obtener catálogos
    getCatalogs: async (): Promise<Catalog[]> => {
        const response = await api.get<Catalog[]>('/api/catalogs');
        return response.data;
    },

    // Obtener medidas
    getMeasures: async (catalogName: string): Promise<Measure[]> => {
        const response = await api.get<Measure[]>(`/api/catalogs/${catalogName}/measures`);
        return response.data;
    },

    // Obtener dimensiones
    getDimensions: async (catalogName: string): Promise<Dimension[]> => {
        const response = await api.get<Dimension[]>(`/api/catalogs/${catalogName}/dimensions`);
        return response.data;
    },

    // Obtener miembros de un nivel
    getMembers: async (
        catalogName: string,
        dimension: string,
        hierarchy: string,
        level: string
    ): Promise<Member[]> => {
        const response = await api.get<Member[]>(`/api/catalogs/${catalogName}/members`, {
            params: { dimension, hierarchy, level },
        });
        return response.data;
    },

    // Ejecutar query
    executeQuery: async (request: QueryRequest): Promise<QueryResponse> => {
        const response = await api.post<QueryResponse>('/api/query/execute', request);
        return response.data;
    },
};
