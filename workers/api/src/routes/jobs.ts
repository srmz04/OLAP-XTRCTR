import { Hono } from 'hono';
import { neon } from '@neondatabase/serverless';

type Bindings = {
    DATABASE_URL: string;
    GH_TOKEN: string;
};

const app = new Hono<{ Bindings: Bindings }>();

// GET /api/jobs/:id
app.get('/:id', async (c) => {
    try {
        const id = c.req.param('id');
        const sql = neon(c.env.DATABASE_URL);

        // Fetch job details
        const result = await sql`
      SELECT 
        id, 
        status, 
        result_data, 
        error_message, 
        created_at, 
        updated_at
      FROM jobs 
      WHERE id = ${id}
    `;

        if (!result || result.length === 0) {
            return c.json({ error: 'Job not found' }, 404);
        }

        // Parse result_data if it exists and is a string (though neon usually handles JSON)
        const job = result[0];

        return c.json({ job });
    } catch (error) {
        console.error('Error fetching job:', error);
        return c.json({ error: 'Failed to fetch job' }, 500);
    }
});

// POST /api/jobs (Create & Trigger)
app.post('/', async (c) => {
    try {
        const body = await c.req.json();
        const { catalog_code, mdx_query } = body;

        if (!catalog_code || !mdx_query) {
            return c.json({ error: 'Missing catalog_code or mdx_query' }, 400);
        }

        const sql = neon(c.env.DATABASE_URL);

        // 1. Create Job in DB
        const result = await sql`
      INSERT INTO jobs (catalog_code, mdx_query, status)
      VALUES (${catalog_code}, ${mdx_query}, 'PENDING')
      RETURNING id
    `;
        const jobId = result[0].id;

        // 2. Trigger GitHub Action
        const repoOwner = 'srmz04';
        const repoName = 'OLAP-XTRCTR';
        const workflowId = 'olap_execution.yml';

        const ghResponse = await fetch(`https://api.github.com/repos/${repoOwner}/${repoName}/actions/workflows/${workflowId}/dispatches`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${c.env.GH_TOKEN}`,
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'OLAP-XTRCTR-API'
            },
            body: JSON.stringify({
                ref: 'master',
                inputs: {
                    job_id: jobId
                }
            })
        });

        if (!ghResponse.ok) {
            const errorText = await ghResponse.text();
            console.error('GitHub Dispatch Failed:', errorText);

            // Mark job as failed immediately if dispatch fails
            await sql`
        UPDATE jobs 
        SET status = 'FAILED', error_message = ${'Failed to trigger GitHub Action: ' + errorText} 
        WHERE id = ${jobId}
      `;

            return c.json({ error: 'Failed to trigger execution runner', details: errorText }, 502);
        }

        return c.json({
            success: true,
            jobId,
            status: 'PENDING',
            message: 'Job created and runner triggered'
        });

    } catch (error) {
        console.error('Error creating job:', error);
        return c.json({
            error: 'Failed to create job',
            message: error instanceof Error ? error.message : 'Unknown error'
        }, 500);
    }
});

export default app;
