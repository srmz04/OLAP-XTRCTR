/**
 * Actions Service - Dispatches GitHub Actions workflows for OLAP queries
 * Polls Gist for results
 */

const GITHUB_OWNER = import.meta.env.VITE_GITHUB_OWNER || 'usuario';
const GITHUB_REPO = import.meta.env.VITE_GITHUB_REPO || 'OLAP-XTRCTR';
const GIST_ID = import.meta.env.VITE_GIST_ID || '';
const GITHUB_TOKEN = import.meta.env.VITE_GITHUB_TOKEN || '';

// API mode: 'actions' for GitHub Actions relay, 'direct' for direct API
const API_MODE = import.meta.env.VITE_API_MODE || 'direct';

interface ActionResult<T> {
    request_id: string;
    action: string;
    status: 'success' | 'error';
    data?: T;
    error?: string;
}

/**
 * Generate unique request ID
 */
function generateRequestId(): string {
    return `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Dispatch a workflow and wait for result
 */
async function dispatchAndWait<T>(
    action: string,
    catalog?: string,
    params?: Record<string, unknown>
): Promise<T> {
    const requestId = generateRequestId();

    console.log(`[ActionsService] Dispatching ${action} (${requestId})...`);

    // Dispatch workflow
    const dispatchResponse = await fetch(
        `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/query_relay.yml/dispatches`,
        {
            method: 'POST',
            headers: {
                'Accept': 'application/vnd.github.v3+json',
                'Authorization': `Bearer ${GITHUB_TOKEN}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                ref: 'master',
                inputs: {
                    action,
                    catalog: catalog || '',
                    params: JSON.stringify(params || {}),
                    request_id: requestId,
                },
            }),
        }
    );

    if (!dispatchResponse.ok) {
        throw new Error(`Failed to dispatch workflow: ${dispatchResponse.status}`);
    }

    console.log(`[ActionsService] Workflow dispatched, polling for result...`);

    // Poll for result
    const maxAttempts = 60; // 5 minutes max
    const pollInterval = 5000; // 5 seconds

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
        await new Promise((resolve) => setTimeout(resolve, pollInterval));

        try {
            const gistResponse = await fetch(
                `https://api.github.com/gists/${GIST_ID}`,
                {
                    headers: {
                        'Accept': 'application/vnd.github.v3+json',
                        'Authorization': `Bearer ${GITHUB_TOKEN}`,
                    },
                }
            );

            if (gistResponse.ok) {
                const gist = await gistResponse.json();
                const resultFile = gist.files[`${requestId}.json`];

                if (resultFile) {
                    const result: ActionResult<T> = JSON.parse(resultFile.content);
                    console.log(`[ActionsService] Result received for ${requestId}`);

                    if (result.status === 'error') {
                        throw new Error(result.error || 'Unknown error');
                    }

                    return result.data as T;
                }
            }
        } catch (e) {
            console.log(`[ActionsService] Poll attempt ${attempt + 1}/${maxAttempts}...`);
        }
    }

    throw new Error('Timeout waiting for result');
}

/**
 * Actions-based catalog service
 */
export const actionsService = {
    isEnabled: () => API_MODE === 'actions' && !!GITHUB_TOKEN && !!GIST_ID,

    getCatalogs: async () => {
        const result = await dispatchAndWait<{ catalogs: any[] }>('get_catalogs');
        return result.catalogs;
    },

    getApartados: async (catalogName: string) => {
        const result = await dispatchAndWait<{ apartados: any[] }>('get_apartados', catalogName);
        return result.apartados;
    },

    getVariables: async (catalogName: string, apartados?: string[]) => {
        const result = await dispatchAndWait<{ variables: any[] }>(
            'get_variables',
            catalogName,
            { apartados }
        );
        return result.variables;
    },

    getDimensions: async (catalogName: string) => {
        const result = await dispatchAndWait<{ dimensions: any[] }>('get_dimensions', catalogName);
        return result.dimensions;
    },

    getMembers: async (
        catalogName: string,
        dimension: string,
        hierarchy: string,
        level: string
    ) => {
        const result = await dispatchAndWait<{ members: any[] }>(
            'get_members',
            catalogName,
            { dimension, hierarchy, level }
        );
        return result.members;
    },

    executeQuery: async (payload: any) => {
        const result = await dispatchAndWait<any>('execute_query', payload.catalog, payload);
        return result;
    },
};
