# Job Hunter API

AI-powered job hunting automation system that converts email job alerts into a pipeline of opportunities with tailored CVs, cover letters, and optional auto-apply functionality.

## Features

- **Email Integration**: Parse job alerts from Gmail/Outlook
- **CV Adaptation**: AI-powered CV customization per job posting
- **Cover Letter Generation**: Contextual cover letters with talking points
- **Browser Automation**: Multiple modes including Local Browser via Chrome Extension
- **Application Tracking**: Pipeline management (Inbox → Applied)
- **Real-time Updates**: WebSocket connections for live application progress
- **Chrome Extension Support**: WebSocket endpoint for local browser automation

## Quick Start

### Prerequisites

- Python 3.11+
- Poetry
- Chrome (for local browser automation)

### Installation

```bash
# Clone and enter directory
cd job-hunter-api

# Install dependencies
poetry install

# Copy environment template
cp .env.example .env

# Edit .env with your API keys
# Required: ANTHROPIC_API_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_PUBLIC_KEY

# Run database migrations
poetry run alembic upgrade head

# Start the server
poetry run uvicorn src.main:app --reload
```

### CLI Usage (with Claude Code)

```bash
# Gmail Integration
poetry run job-hunter gmail-login     # Authenticate with Gmail
poetry run job-hunter gmail-status    # Check connection status
poetry run job-hunter gmail-fetch     # Fetch job alert emails
poetry run job-hunter gmail-logout    # Disconnect Gmail

# Adapt CV for a specific job
poetry run job-hunter adapt-cv \
  --cv ./my_cv.pdf \
  --job "Job description text or file path" \
  --title "Software Engineer" \
  --company "Acme Corp"

# Generate cover letter
poetry run job-hunter cover-letter \
  --cv ./my_cv.pdf \
  --job "Job description..." \
  --title "Software Engineer" \
  --company "Acme Corp"

# Browser Automation (Phase 2)
poetry run job-hunter browser-start                    # Start browser service
poetry run job-hunter apply <url> --cv ./cv.pdf       # Apply to job (assisted mode)
poetry run job-hunter apply-status <session_id>       # Check application status
poetry run job-hunter apply-resume <session_id>       # Resume paused application

# Show configuration
poetry run job-hunter info
```

### API Usage

```bash
# With your own API key
curl -X POST http://localhost:8000/api/jobs/adapt \
  -H "X-Anthropic-Api-Key: sk-ant-..." \
  -H "Content-Type: application/json" \
  -d '{"job_url": "https://...", "cv_content": "..."}'
```

### Chrome Extension WebSocket

The API provides a WebSocket endpoint for the Chrome Extension to enable Local Browser mode:

```
wss://job-hunter-api-kdyd.onrender.com/api/ws/extension
```

**Connection flow:**
1. Extension connects to WebSocket endpoint
2. Dashboard initiates application with `mode: LOCAL_BROWSER`
3. API sends commands to extension: `navigate`, `analyze`, `fill`
4. Extension executes in user's browser and reports results

## Project Structure

```
job-hunter-api/
├── src/
│   ├── agents/           # AI Agents (CV adapter, form filler, question answerer)
│   ├── api/              # FastAPI routes (jobs, users, applications)
│   ├── automation/       # Browser automation
│   │   ├── strategies/   # ATS-specific strategies (Breezy, Generic)
│   │   ├── blockers/     # CAPTCHA & blocker detection
│   │   ├── client.py     # Browser service HTTP client
│   │   └── pause_manager.py  # Session state management
│   ├── browser_service/  # Standalone browser service (port 8001)
│   │   └── adapters/     # Chrome DevTools MCP, Playwright
│   ├── cli/              # Typer CLI commands
│   ├── db/               # SQLAlchemy models
│   ├── integrations/     # Claude SDK, Gmail, Langfuse
│   └── mcp/              # MCP client wrapper
├── docs/                 # Implementation tracking
└── tests/
```

## Documentation

- [Implementation Status](docs/IMPLEMENTATION_STATUS.md)
- [Tech Stack](docs/TECH_STACK.md)
- [Agents Status](docs/AGENTS_STATUS.md)
- [Blockers Log](docs/BLOCKERS_LOG.md)
- [API Integration](docs/API_INTEGRATION.md)
- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md)

## License

MIT
