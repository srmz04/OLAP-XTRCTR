// src/api/client.ts
import type { CatalogsResponse, MembersResponse } from '../types/olap';

const API_URL = import.meta.env.VITE_API_URL || 'https://olap-api.xtrctr.workers.dev/api';

export const olapApi = {
    async getCatalogs(): Promise<CatalogsResponse> {
        const response = await fetch(`${API_URL}/catalogs`);
        if (!response.ok) {
            throw new Error(`Failed to fetch catalogs: ${response.statusText}`);
        }
        return response.json();
    },

    async getMembers(
        catalog: string,
        nivel?: 'Apartado' | 'Variable',
        parent?: string,
        limit = 1000,
        offset = 0
    ): Promise<MembersResponse> {
        const params = new URLSearchParams({
            ...(nivel && { nivel }),
            ...(parent && { parent }),
            limit: limit.toString(),
            offset: offset.toString(),
        });

        const response = await fetch(`${API_URL}/members/${catalog}?${params}`);
        if (!response.ok) {
            throw new Error(`Failed to fetch members: ${response.statusText}`);
        }
        return response.json();
    },

    async getApartados(catalog: string, limit = 1000): Promise<MembersResponse> {
        return this.getMembers(catalog, 'Apartado', undefined, limit);
    },

    async getVariables(catalog: string, limit = 1000): Promise<MembersResponse> {
        return this.getMembers(catalog, 'Variable', undefined, limit);
    },

    async getVariablesOfApartado(catalog: string, apartadoUniqueName: string, limit = 1000): Promise<MembersResponse> {
        return this.getMembers(catalog, 'Variable', apartadoUniqueName, limit);
    },
};
```
