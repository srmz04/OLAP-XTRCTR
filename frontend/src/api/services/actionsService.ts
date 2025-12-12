/**
 * Actions Service - Hybrid Cache Architecture
 * 
 * Uses SmartCache for 3-tier caching:
 * - L1: Memory (instant)
 * - L2: localStorage (persistent)
 * - L3: Gist (shared)
 * 
 * Falls back to workflow dispatch when cache miss on critical data
 */

import { smartCache } from '../../utils/cache';

const GITHUB_OWNER = import.meta.env.VITE_GITHUB_OWNER || 'srmz04';
const GITHUB_REPO = import.meta.env.VITE_GITHUB_REPO || 'OLAP-XTRCTR';
const GITHUB_TOKEN = import.meta.env.VITE_GITHUB_TOKEN || '';
const GIST_ID = import.meta.env.VITE_GIST_ID || '';
const API_MODE = import.meta.env.VITE_API_MODE || 'direct';

// Cache keys
const CACHE_KEYS = {
    catalogs: 'catalogs',
    structure: (catalog: string) => `${catalog}_structure`,
    apartados: (catalog: string) => `${catalog}_apartados`,
    variables: (catalog: string, apartado: string) => `${catalog}_vars_${apartado}`,
    dimensions: (catalog: string) => `${catalog}_dimensions`,
    members: (catalog: string, dim: string) => `${catalog}_members_${dim}`,
};

// Special TTLs
const TTL = {
    catalogs: 30 * 24 * 60 * 60 * 1000, // 30 days - rarely changes
    structure: 7 * 24 * 60 * 60 * 1000,  // 7 days
    apartados: 7 * 24 * 60 * 60 * 1000,  // 7 days - 27K items
    default: 24 * 60 * 60 * 1000,         // 1 day
};

interface CatalogInfo {
    name: string;
    description?: string;
    created?: string;
}

interface ApartadoInfo {
    MEMBER_UNIQUE_NAME: string;
    MEMBER_CAPTION: string;
}

interface DimensionInfo {
    cube_name: string;
    dimension: string;
}

/**
 * Dispatch workflow and wait for result (with timeout)
 */
async function dispatchAndWait(
    action: string,
    catalog: string,
    params: Record<string, unknown> = {},
    timeoutMs = 120000
): Promise<unknown> {
    const requestId = `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    console.log(`[ActionsService] Dispatching ${action} (${requestId})...`);

    // Dispatch workflow
    const dispatchResponse = await fetch(
        `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/query_relay.yml/dispatches`,
        {
            method: 'POST',
            headers: {
                Authorization: `Bearer ${GITHUB_TOKEN}`,
                Accept: 'application/vnd.github.v3+json',
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                ref: 'master',
                inputs: {
                    action,
                    catalog,
                    params: JSON.stringify(params),
                    request_id: requestId,
                },
            }),
        }
    );

    if (!dispatchResponse.ok) {
        const error = await dispatchResponse.text();
        throw new Error(`Workflow dispatch failed: ${dispatchResponse.status} - ${error}`);
    }

    // Poll Gist for result
    const startTime = Date.now();
    const pollInterval = 5000; // 5 seconds

    while (Date.now() - startTime < timeoutMs) {
        await new Promise(resolve => setTimeout(resolve, pollInterval));

        // Invalidate cache and check for new result
        smartCache.invalidateGistCache();

        // Check Gist directly for the request result
        try {
            // CACHE BUSTING: Add timestamp to avoid caching (304 Not Modified)
            const response = await fetch(`https://api.github.com/gists/${GIST_ID}?t=${Date.now()}`, {
                headers: {
                    Authorization: `Bearer ${GITHUB_TOKEN}`,
                    Accept: 'application/vnd.github.v3+json',
                },
            });

            if (response.ok) {
                const gist = await response.json();
                const resultFile = gist.files[`${requestId}.json`];

                if (resultFile) {
                    const result = JSON.parse(resultFile.content);
                    console.log(`[ActionsService] Result received for ${requestId}`);
                    return result.data;
                }
            }
        } catch (e) {
            console.warn('[ActionsService] Poll check failed:', e);
        }

        console.log(`[ActionsService] Waiting... (${Math.round((Date.now() - startTime) / 1000)}s)`);
    }

    throw new Error(`Timeout waiting for workflow result: ${requestId}`);
}

/**
 * Actions-based catalog service with hybrid cache
 */
export const actionsService = {
    isEnabled: () => API_MODE === 'actions' && !!GIST_ID,

    /**
     * Get catalogs - cache first, dispatch if miss
     */
    getCatalogs: async (): Promise<CatalogInfo[]> => {
        const cacheKey = CACHE_KEYS.catalogs;

        // Check cache
        const cached = await smartCache.get<CatalogInfo[]>(cacheKey);
        if (cached) {
            return cached;
        }

        // Cache miss - dispatch workflow
        console.log('[ActionsService] Cache miss for catalogs, dispatching...');
        const result = await dispatchAndWait('get_catalogs', '') as { catalogs: CatalogInfo[] };

        // Save to cache
        await smartCache.set(cacheKey, result.catalogs, TTL.catalogs);

        return result.catalogs;
    },

    /**
     * Get structure (dimensions) of a catalog
     */
    getStructure: async (catalogName: string): Promise<DimensionInfo[]> => {
        const cacheKey = CACHE_KEYS.structure(catalogName);

        const cached = await smartCache.get<DimensionInfo[]>(cacheKey);
        if (cached) {
            return cached;
        }

        console.log(`[ActionsService] Cache miss for ${catalogName} structure, dispatching...`);
        const result = await dispatchAndWait('discover_structure', catalogName) as { dimensions: DimensionInfo[] };

        await smartCache.set(cacheKey, result.dimensions, TTL.structure);

        return result.dimensions;
    },

    /**
     * Get apartados (variables) - large dataset, prefer cache
     */
    getApartados: async (catalogName: string): Promise<ApartadoInfo[]> => {
        const cacheKey = CACHE_KEYS.apartados(catalogName);

        const cached = await smartCache.get<ApartadoInfo[]>(cacheKey);
        if (cached) {
            return cached;
        }

        console.log(`[ActionsService] Cache miss for ${catalogName} apartados, dispatching...`);
        const result = await dispatchAndWait('get_apartados', catalogName) as { apartados: ApartadoInfo[] };

        await smartCache.set(cacheKey, result.apartados, TTL.apartados);

        return result.apartados;
    },

    /**
     * Get variables for selected apartados
     */
    getVariables: async (catalogName: string, _apartados?: string[]): Promise<ApartadoInfo[]> => {
        // Variables are children of apartados - for now return from cache if available
        const cacheKey = CACHE_KEYS.apartados(catalogName) + '_vars';

        const cached = await smartCache.get<ApartadoInfo[]>(cacheKey);
        if (cached) {
            return cached;
        }

        console.log(`[ActionsService] Variables not cached for ${catalogName}`);
        // Return empty - variables require specific query
        return [];
    },

    /**
     * Get dimensions for filtering
     */
    getDimensions: async (catalogName: string): Promise<DimensionInfo[]> => {
        // Alias for getStructure
        return actionsService.getStructure(catalogName);
    },

    /**
     * Get members of a dimension
     */
    getMembers: async (
        catalogName: string,
        dimension: string,
        _hierarchy?: string,
        _level?: string
    ): Promise<ApartadoInfo[]> => {
        const cacheKey = CACHE_KEYS.members(catalogName, dimension.replace(/[\[\]]/g, ''));

        const cached = await smartCache.get<ApartadoInfo[]>(cacheKey);
        if (cached) {
            return cached;
        }

        console.log(`[ActionsService] Cache miss for ${catalogName}/${dimension} members`);
        // For now, return empty - user should pre-cache via workflow
        return [];
    },

    /**
     * Execute MDX query - not cached by default
     */
    executeQuery: async (payload: {
        catalog: string;
        mdx?: string;
        filters?: Array<{ member_unique_name: string }>;
    }): Promise<{ rows: unknown[]; columns: unknown[]; rowCount: number; error?: string }> => {
        console.log('[ActionsService] Executing query...');

        try {
            const result = await dispatchAndWait('execute_mdx', payload.catalog, {
                mdx: payload.mdx,
            }) as { rows: unknown[]; columns: unknown[]; rowCount: number; error?: string };

            return result;
        } catch (e) {
            return {
                rows: [],
                columns: [],
                rowCount: 0,
                error: e instanceof Error ? e.message : 'Unknown error',
            };
        }
    },

    /**
     * Clear all cache
     */
    clearCache: async (): Promise<void> => {
        await smartCache.clearAll();
        console.log('[ActionsService] Cache cleared');
    },

    /**
     * Preload common data into cache
     */
    preloadCache: async (): Promise<void> => {
        console.log('[ActionsService] Preloading cache...');

        try {
            // Load catalogs
            await actionsService.getCatalogs();
            console.log('[ActionsService] Catalogs preloaded');
        } catch (e) {
            console.warn('[ActionsService] Preload failed:', e);
        }
    },
};

export type { CatalogInfo, ApartadoInfo, DimensionInfo };
