/**
 * Actions Service - Pre-cache architecture
 * Reads cached data from Gist, only dispatches for dynamic queries
 */

const GIST_ID = import.meta.env.VITE_GIST_ID || '';
const GITHUB_TOKEN = import.meta.env.VITE_GITHUB_TOKEN || '';
const API_MODE = import.meta.env.VITE_API_MODE || 'direct';

// Cache for Gist data
let gistCache: Record<string, any> | null = null;
let cacheTimestamp = 0;
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

/**
 * Fetch entire Gist and cache it
 */
async function fetchGistData(): Promise<Record<string, any>> {
    const now = Date.now();

    // Return cached data if still valid
    if (gistCache && (now - cacheTimestamp) < CACHE_TTL) {
        return gistCache;
    }

    if (!GIST_ID) {
        throw new Error('GIST_ID not configured');
    }

    console.log('[ActionsService] Fetching Gist cache...');

    const response = await fetch(`https://api.github.com/gists/${GIST_ID}`, {
        headers: {
            'Accept': 'application/vnd.github.v3+json',
            ...(GITHUB_TOKEN ? { 'Authorization': `Bearer ${GITHUB_TOKEN}` } : {})
        }
    });

    if (!response.ok) {
        throw new Error(`Failed to fetch Gist: ${response.status}`);
    }

    const gist = await response.json();

    // Parse all JSON files in the Gist
    const data: Record<string, any> = {};
    for (const [filename, file] of Object.entries(gist.files)) {
        if (filename.endsWith('.json')) {
            try {
                data[filename] = JSON.parse((file as any).content);
            } catch {
                data[filename] = (file as any).content;
            }
        }
    }

    gistCache = data;
    cacheTimestamp = now;

    console.log('[ActionsService] Gist cache loaded:', Object.keys(data));
    return data;
}

/**
 * Get cached catalogs from Gist
 */
async function getCachedCatalogs(): Promise<any[]> {
    const data = await fetchGistData();

    // Look for catalogs cache file
    const catalogsFile = data['catalogs_cache.json'] || data['test_002.json'];

    if (catalogsFile && catalogsFile.data && catalogsFile.data.catalogs) {
        return catalogsFile.data.catalogs;
    }

    // Try to find any request with get_catalogs action
    for (const [filename, content] of Object.entries(data)) {
        if (content && content.action === 'get_catalogs' && content.status === 'success') {
            return content.data.catalogs;
        }
    }

    throw new Error('No cached catalogs found in Gist');
}

/**
 * Actions-based catalog service with pre-cache
 */
export const actionsService = {
    isEnabled: () => API_MODE === 'actions' && !!GIST_ID,

    getCatalogs: async () => {
        // Always read from cache, no dispatch needed
        return getCachedCatalogs();
    },

    getApartados: async (catalogName: string) => {
        const data = await fetchGistData();
        const cacheFile = data[`apartados_${catalogName}.json`];

        if (cacheFile && cacheFile.data && cacheFile.data.apartados) {
            return cacheFile.data.apartados;
        }

        // If not cached, return empty (user needs to run workflow manually)
        console.warn(`[ActionsService] No cached apartados for ${catalogName}. Run query_relay workflow manually.`);
        return [];
    },

    getVariables: async (catalogName: string, apartados?: string[]) => {
        const data = await fetchGistData();
        const cacheFile = data[`variables_${catalogName}.json`];

        if (cacheFile && cacheFile.data && cacheFile.data.variables) {
            return cacheFile.data.variables;
        }

        console.warn(`[ActionsService] No cached variables for ${catalogName}.`);
        return [];
    },

    getDimensions: async (catalogName: string) => {
        const data = await fetchGistData();
        const cacheFile = data[`dimensions_${catalogName}.json`];

        if (cacheFile && cacheFile.data && cacheFile.data.dimensions) {
            return cacheFile.data.dimensions;
        }

        console.warn(`[ActionsService] No cached dimensions for ${catalogName}.`);
        return [];
    },

    getMembers: async (
        catalogName: string,
        dimension: string,
        hierarchy: string,
        level: string
    ) => {
        const data = await fetchGistData();
        const cacheFile = data[`members_${catalogName}_${dimension}.json`];

        if (cacheFile && cacheFile.data && cacheFile.data.members) {
            return cacheFile.data.members;
        }

        console.warn(`[ActionsService] No cached members for ${catalogName}/${dimension}.`);
        return [];
    },

    executeQuery: async (payload: any) => {
        // For queries, we would need to dispatch - but for now return empty
        console.warn('[ActionsService] Query execution requires manual workflow dispatch.');
        return { rows: [], columns: [], rowCount: 0, error: 'Use manual workflow dispatch for queries' };
    },
};
