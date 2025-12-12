# Job Hunter API

AI-powered job hunting automation system that converts email job alerts into a pipeline of opportunities with tailored CVs, cover letters, and optional auto-apply functionality.

## Features

- **Email Integration**: Parse job alerts from Gmail/Outlook
- **CV Adaptation**: AI-powered CV customization per job posting
- **Cover Letter Generation**: Contextual cover letters with talking points
- **Browser Automation**: Form filling via MCP (Chrome DevTools / Playwright)
- **Application Tracking**: Pipeline management (Inbox → Applied)

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
poetry run python -m src.cli.commands gmail-login     # Authenticate with Gmail
poetry run python -m src.cli.commands gmail-status    # Check connection status
poetry run python -m src.cli.commands gmail-fetch     # Fetch job alert emails
poetry run python -m src.cli.commands gmail-logout    # Disconnect Gmail

# Adapt CV for a specific job
poetry run python -m src.cli.commands adapt-cv \
  --cv ./my_cv.pdf \
  --job "Job description text or file path" \
  --title "Software Engineer" \
  --company "Acme Corp"

# Generate cover letter
poetry run python -m src.cli.commands cover-letter \
  --cv ./my_cv.pdf \
  --job "Job description..." \
  --title "Software Engineer" \
  --company "Acme Corp"

# Show configuration
poetry run python -m src.cli.commands info
```

### API Usage

```bash
# With your own API key
curl -X POST http://localhost:8000/api/jobs/adapt \
  -H "X-Anthropic-Api-Key: sk-ant-..." \
  -H "Content-Type: application/json" \
  -d '{"job_url": "https://...", "cv_content": "..."}'
```

## Project Structure

```
job-hunter-api/
├── src/
│   ├── agents/           # AI Agents (CV adapter, form filler, etc.)
│   ├── api/              # FastAPI routes
│   ├── automation/       # ATS-specific instructions
│   ├── cli/              # Typer CLI commands
│   ├── db/               # SQLAlchemy models
│   ├── integrations/     # Claude SDK, Email, Langfuse
│   └── mcp/              # MCP browser client
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
