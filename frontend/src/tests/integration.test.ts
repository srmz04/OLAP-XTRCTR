
import { describe, it, expect } from 'vitest';
import axios from 'axios';

// The backend URL in GitHub Actions (Service or Background Process)
// In the workflow, we will set VITE_API_URL or default to localhost:8000
const BASE_URL = process.env.VITE_API_URL || 'http://localhost:8000/api';

describe('OLAP Backend Integration Tests', () => {

    it('should be reachable', async () => {
        try {
            const health = await axios.get(`${BASE_URL}/catalogs`);
            // Note: /api/catalogs is the endpoint. 
            // If BASE_URL includes /api, we just add /catalogs? No, usually BASE_URL is root API.
            // Let's assume BASE_URL = http://localhost:8000/api

            expect(health.status).toBe(200);
            expect(Array.isArray(health.data)).toBe(true);
            console.log("✅ Catalogs found:", health.data.length);
        } catch (error) {
            console.error("❌ Connection failed:", error.message);
            throw error;
        }
    });

    it('should fetch variables for the first catalog', async () => {
        const catalogs = await axios.get(`${BASE_URL}/catalogs`);
        if (catalogs.data.length > 0) {
            const firstCatalog = catalogs.data[0].name;
            const variables = await axios.get(`${BASE_URL}/catalogs/${firstCatalog}/variables`);
            expect(variables.status).toBe(200);
            expect(Array.isArray(variables.data)).toBe(true);
            console.log(`✅ Variables for ${firstCatalog}:`, variables.data.length);
        } else {
            console.warn("⚠️ No catalogs to test variables against.");
        }
    });
});
