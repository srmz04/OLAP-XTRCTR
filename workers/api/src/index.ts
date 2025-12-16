// src/index.ts - Main API entry point
import { Hono } from 'hono';
import { cors } from 'hono/cors';
import catalogs from './routes/catalogs';
import members from './routes/members';
import jobs from './routes/jobs';

type Bindings = {
    DATABASE_URL: string;
    GH_TOKEN: string;
};

const app = new Hono<{ Bindings: Bindings }>();

// CORS middleware (allow all origins for now)
app.use('/*', cors({
    origin: '*',
    allowMethods: ['GET', 'POST', 'OPTIONS'],
    allowHeaders: ['Content-Type'],
}));

// Health check
app.get('/', (c) => {
    return c.json({
        status: 'ok',
        version: '3.0.0',
        timestamp: new Date().toISOString()
    });
});

// Mount routes
app.route('/api/catalogs', catalogs);
app.route('/api/members', members);
app.route('/api/jobs', jobs);

// 404 handler
app.notFound((c) => {
    return c.json({ error: 'Not found' }, 404);
});

// Error handler
app.onError((err, c) => {
    console.error(err);
    return c.json({ error: 'Internal server error', message: err.message }, 500);
});

export default app;
