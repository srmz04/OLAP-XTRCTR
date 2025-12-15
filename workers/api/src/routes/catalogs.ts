// src/routes/catalogs.ts - Catalog listing endpoint
import { Hono } from 'hono';
import { neon } from '@neondatabase/serverless';

type Bindings = {
    DATABASE_URL: string;
};

const app = new Hono<{ Bindings: Bindings }>();

// GET /api/catalogs
app.get('/', async (c) => {
    try {
        const sql = neon(c.env.DATABASE_URL);

        const catalogs = await sql`
      SELECT code, name, year
      FROM catalogs
      ORDER BY year DESC, code ASC
    `;

        return c.json({
            catalogs,
            count: catalogs.length,
            timestamp: new Date().toISOString()
        });
    } catch (error) {
        console.error('Error fetching catalogs:', error);
        return c.json({ error: 'Failed to fetch catalogs' }, 500);
    }
});

export default app;
