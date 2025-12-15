// src/routes/members.ts - Members endpoint with filtering
import { Hono } from 'hono';
import { neon } from '@neondatabase/serverless';

type Bindings = {
    DATABASE_URL: string;
};

const app = new Hono<{ Bindings: Bindings }>();

// GET /api/members/:catalog?nivel=Apartado&limit=1000
app.get('/:catalog', async (c) => {
    try {
        const catalog = c.req.param('catalog');
        const nivel = c.req.query('nivel'); // 'Apartado' | 'Variable' | undefined
        const limit = parseInt(c.req.query('limit') || '1000', 10);
        const offset = parseInt(c.req.query('offset') || '0', 10);

        const sql = neon(c.env.DATABASE_URL);

        // Build query based on nivel filter
        let members;
        if (nivel) {
            members = await sql`
        SELECT 
          caption,
          unique_name,
          level_name,
          children_cardinality,
          parent_unique_name
        FROM v_members_full
        WHERE catalog_code = ${catalog} 
          AND level_name = ${nivel}
        ORDER BY caption
        LIMIT ${limit}
        OFFSET ${offset}
      `;
        } else {
            members = await sql`
        SELECT 
          caption,
          unique_name,
          level_name,
          level_number,
          children_cardinality,
          parent_unique_name
        FROM v_members_full
        WHERE catalog_code = ${catalog}
        ORDER BY level_number, caption
        LIMIT ${limit}
        OFFSET ${offset}
      `;
        }

        // Get total count for pagination
        const countResult = nivel
            ? await sql`
          SELECT COUNT(*) as total
          FROM v_members_full
          WHERE catalog_code = ${catalog} AND level_name = ${nivel}
        `
            : await sql`
          SELECT COUNT(*) as total
          FROM v_members_full
          WHERE catalog_code = ${catalog}
        `;

        const total = parseInt(countResult[0]?.total || '0', 10);

        return c.json({
            catalog,
            nivel: nivel || 'all',
            members,
            count: members.length,
            total,
            limit,
            offset,
            timestamp: new Date().toISOString()
        });
    } catch (error) {
        console.error('Error fetching members:', error);
        return c.json({
            error: 'Failed to fetch members',
            message: error instanceof Error ? error.message : 'Unknown error'
        }, 500);
    }
});

export default app;
