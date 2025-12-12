# Deployment Guide

> Last Updated: 2025-12-11
> Supported: Local CLI | Render | Vercel (Dashboard)

## Environment Overview

| Environment | Purpose | Platform | Database |
|-------------|---------|----------|----------|
| Local | Development | CLI + FastAPI | SQLite |
| Staging | Testing | Render | PostgreSQL |
| Production | Live | Render | PostgreSQL |

---

## Local Development

### Prerequisites

- Python 3.11+
- Poetry
- Chrome (for MCP browser automation)
- Node.js (for Chrome DevTools MCP)

### Setup

```bash
# Clone repository
git clone <repo-url>
cd job-hunter-api

# Install dependencies
poetry install

# Copy environment template
cp .env.example .env

# Edit .env with your API keys
# Required:
# - ANTHROPIC_API_KEY
# - LANGFUSE_SECRET_KEY
# - LANGFUSE_PUBLIC_KEY

# Create data directory
mkdir -p data

# Run database migrations
poetry run alembic upgrade head

# Start development server
poetry run uvicorn src.main:app --reload --port 8000
```

### CLI Usage

```bash
# Run CLI commands
poetry run job-hunter --help

# Adapt CV
poetry run job-hunter adapt-cv --job-url "https://..." --cv-path "./cv.pdf"

# Parse email
poetry run job-hunter parse-email --message-id "..."
```

### MCP Browser Setup (Local)

```bash
# Start Chrome with remote debugging
# Windows:
chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\temp\chrome-debug"

# Mac:
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="/tmp/chrome-debug"

# Then use Claude Code with MCP
claude --mcp chrome
```

---

## Render Deployment

### Initial Setup

1. Create account at [render.com](https://render.com)
2. Connect GitHub repository
3. Create PostgreSQL database
4. Create Web Service

### render.yaml

```yaml
services:
  - type: web
    name: job-hunter-api
    runtime: python
    buildCommand: pip install poetry && poetry install --no-dev
    startCommand: poetry run uvicorn src.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: job-hunter-db
          property: connectionString
      - key: LANGFUSE_SECRET_KEY
        sync: false
      - key: LANGFUSE_PUBLIC_KEY
        sync: false
      - key: LANGFUSE_BASE_URL
        value: https://cloud.langfuse.com
      - key: APP_ENV
        value: production
    healthCheckPath: /health

databases:
  - name: job-hunter-db
    plan: starter
```

### Environment Variables (Render Dashboard)

| Variable | Required | Notes |
|----------|----------|-------|
| `DATABASE_URL` | Yes | Auto-set from database |
| `LANGFUSE_SECRET_KEY` | Yes | From Langfuse dashboard |
| `LANGFUSE_PUBLIC_KEY` | Yes | From Langfuse dashboard |
| `LANGFUSE_BASE_URL` | Yes | https://cloud.langfuse.com |
| `ENCRYPTION_KEY` | Yes | Generate with `openssl rand -hex 32` |
| `APP_ENV` | Yes | `production` |

**Note:** `ANTHROPIC_API_KEY` is NOT stored on server - users provide their own via header.

### Deployment

```bash
# Automatic on push to main
git push origin main

# Or manual via Render dashboard
```

---

## API with User API Key

Users provide their Claude API key in requests:

```bash
curl -X POST https://job-hunter-api.onrender.com/api/jobs/adapt \
  -H "X-Anthropic-Api-Key: sk-ant-..." \
  -H "Content-Type: application/json" \
  -d '{
    "job_url": "https://...",
    "cv_content": "..."
  }'
```

---

## MCP for Cloud (Playwright)

For browser automation in cloud environments, use Playwright MCP with HTTP transport:

### Option 1: Sidecar Service

```yaml
# render.yaml - add worker
services:
  - type: worker
    name: playwright-mcp
    runtime: docker
    dockerfilePath: ./Dockerfile.playwright
    envVars:
      - key: MCP_PORT
        value: "3000"
```

### Option 2: External Service

Use a hosted Playwright MCP service and configure:

```json
{
  "mcpServers": {
    "playwright": {
      "url": "https://playwright-mcp-service.example.com",
      "transport": "http"
    }
  }
}
```

---

## Health Checks

```python
# src/api/routes/health.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "0.1.0"
    }
```

---

## Monitoring

### Langfuse Dashboard

- URL: https://cloud.langfuse.com
- View traces, token usage, costs
- Set up alerts for errors

### Render Logs

```bash
# Via Render Dashboard
# Service > Logs

# Or CLI
render logs job-hunter-api
```

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| 504 Timeout | Long operation | Increase timeout in render.yaml |
| Missing env vars | Not set | Check Render Environment tab |
| DB connection | Wrong URL | Use internal URL |
| CORS errors | Missing headers | Add CORS middleware |

---

## CI/CD Pipeline

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install poetry
      - run: poetry install
      - run: poetry run pytest
      - run: poetry run ruff check .
      - run: poetry run mypy src/

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to Render
        run: curl -X POST ${{ secrets.RENDER_DEPLOY_HOOK }}
```
