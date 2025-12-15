// src/routes/members.ts - Members endpoint with filtering
import { Hono } from 'hono';
import { neon } from '@neondatabase/serverless';

type Bindings = {
  DATABASE_URL: string;
};

const app = new Hono<{ Bindings: Bindings }>();

// GET /api/members/:catalog?nivel=Apartado&parent=...
app.get('/:catalog', async (c) => {
  try {
    const catalog = c.req.param('catalog');
    const nivel = c.req.query('nivel'); // 'Apartado' | 'Variable' | undefined
    const parent = c.req.query('parent'); // Filter by parent_unique_name
    const limit = parseInt(c.req.query('limit') || '1000', 10);
    const offset = parseInt(c.req.query('offset') || '0', 10);

    const sql = neon(c.env.DATABASE_URL);

    // Build query based on filters
    let members;
    if (nivel && parent) {
      // Filter by both nivel and parent
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
          AND parent_unique_name = ${parent}
        ORDER BY caption
        LIMIT ${limit}
        OFFSET ${offset}
      `;
    } else if (nivel) {
      // Filter by nivel only
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
    } else if (parent) {
      // Filter by parent only
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
          AND parent_unique_name = ${parent}
        ORDER BY level_number, caption
        LIMIT ${limit}
        OFFSET ${offset}
      `;
    } else {
      // No filters
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
    const countResult = nivel && parent
      ? await sql`
          SELECT COUNT(*) as total
          FROM v_members_full
          WHERE catalog_code = ${catalog} AND level_name = ${nivel} AND parent_unique_name = ${parent}
        `
      : nivel
        ? await sql`
          SELECT COUNT(*) as total
          FROM v_members_full
          WHERE catalog_code = ${catalog} AND level_name = ${nivel}
        `
        : parent
          ? await sql`
          SELECT COUNT(*) as total
          FROM v_members_full
          WHERE catalog_code = ${catalog} AND parent_unique_name = ${parent}
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
      parent: parent || null,
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
