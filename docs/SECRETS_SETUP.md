# 🔐 Secrets Configuration Guide

## Required Secrets

To enable the async execution flow, you need to configure the following secrets:

### 1. Cloudflare Workers (API)

The API needs a GitHub Personal Access Token to trigger workflow dispatches.

**Secret Name:** `GH_TOKEN`

**Steps:**
```bash
cd workers/api

# Set the secret (you'll be prompted to enter the value)
wrangler secret put GH_TOKEN
```

**How to get a GitHub Token:**
1. Go to https://github.com/settings/tokens
2. Click "Generate new token" → "Generate new token (classic)"
3. Name: `OLAP-XTRCTR-API`
4. Scopes: Select `repo` (Full control of private repositories)
5. Click "Generate token"
6. Copy the token (starts with `ghp_...`)
7. Paste it when prompted by `wrangler secret put GH_TOKEN`

### 2. GitHub Actions (Runner)

The workflow needs access to PostgreSQL to update job status.

**Secret Name:** `DATABASE_URL`

**Steps:**
1. Go to https://github.com/srmz04/OLAP-XTRCTR/settings/secrets/actions
2. Click "New repository secret"
3. Name: `DATABASE_URL`
4. Value: Your Neon PostgreSQL connection string
   ```
   postgresql://neondb_owner:npg_BjrDI4KY9VTS@ep-floral-silence-ahnwkst0-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require
   ```
5. Click "Add secret"

### 3. Verify Existing Secrets

Make sure these secrets are already configured in GitHub:

```bash
# GitHub Repository Secrets (should already exist)
- DGIS_SERVER
- DGIS_USER
- DGIS_PASSWORD
```

## Testing the Flow

Once secrets are configured:

1. Open http://localhost:5173/
2. Select catalog → apartados → variables
3. Click "Ejecutar Query"
4. Watch the status change: Enviando... → Ejecutando... → Results!

The execution happens on GitHub Actions (Windows) and results are stored in PostgreSQL.

## Troubleshooting

**If execution fails:**
1. Check GitHub Actions logs: https://github.com/srmz04/OLAP-XTRCTR/actions
2. Verify secrets are set correctly
3. Check API logs in Cloudflare dashboard
4. Query the `jobs` table in PostgreSQL to see job status

```sql
SELECT id, status, error_message, created_at 
FROM jobs 
ORDER BY created_at DESC 
LIMIT 10;
```
