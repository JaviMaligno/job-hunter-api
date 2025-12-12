# Technology Stack

> Last Updated: 2025-12-12
> Version: 1.1

## Overview

This document captures all technology decisions for the Job Hunter API project.

---

## Core Technologies

### Runtime & Language

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| Language | Python | 3.11+ | Claude SDK native support, async, ML ecosystem |
| Package Manager | Poetry | Latest | Dependency management, lockfile, scripts |

---

### AI/LLM Integration

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| LLM Provider | Anthropic Claude | claude-sonnet-4.5 | Best reasoning for CV adaptation |
| SDK | anthropic | ^0.40.0 | Official Python SDK (supports Bedrock) |
| AWS Integration | boto3 | ^1.42.0 | Bedrock runtime access |
| Agent Framework | LangGraph | ^0.2.0 | State machine orchestration |
| Observability | Langfuse | ^2.54.0 | Tracing, cost tracking |

**Claude Access Options:**
1. **AWS Bedrock (Preferred):** Uses `AnthropicBedrock` client with AWS credentials
   - Region: `eu-west-2`
   - Model: `eu.anthropic.claude-sonnet-4-5-20250929-v1:0`
2. **Direct Anthropic API:** Uses `Anthropic` client with API key

---

### Web Framework

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| API Framework | FastAPI | ^0.115.0 | Async, OpenAPI, type hints |
| Server | Uvicorn | ^0.32.0 | ASGI, production-ready |
| Validation | Pydantic | ^2.10.0 | Data validation, settings |

---

### Database

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| ORM | SQLAlchemy | ^2.0.0 | Async support, mature |
| Migrations | Alembic | ^1.14.0 | Schema versioning |
| Local DB | SQLite + aiosqlite | - | Simple for development |
| Production DB | PostgreSQL + asyncpg | - | Render managed |

---

### Browser Automation (MCP)

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Local | Chrome DevTools MCP | stdio transport, POC validated |
| Cloud | Playwright MCP | HTTP transport for Render |
| SDK | mcp | ^1.0.0 | Official MCP Python SDK |

**Decision:** Use MCP instead of Playwright directly so the agent has native tool access.

---

### Email Integration

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| Gmail | google-api-python-client | ^2.150.0 | Official API |
| Gmail OAuth | google-auth-oauthlib | ^1.2.0 | Desktop App flow |
| Outlook | O365 | ^2.0.35 | Microsoft Graph wrapper |

**Gmail OAuth Configuration:**
- OAuth Type: Desktop App (Installed Application)
- Scopes: `gmail.readonly`, `gmail.labels`
- Token Storage: `data/gmail_token.json`
- Flow: `InstalledAppFlow.run_local_server(port=0)`

---

### CLI

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| Framework | Typer | ^0.14.0 | Click-based, type hints |

---

### Document Parsing

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| PDF | pypdf | ^5.1.0 | Text extraction |
| DOCX | python-docx | ^1.1.0 | Word document parsing |

---

### Security

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| Encryption | cryptography | ^43.0.0 | API key encryption at rest |

---

## Development Tools

| Tool | Purpose |
|------|---------|
| ruff | Linting + formatting |
| mypy | Type checking |
| pytest | Testing |
| pre-commit | Git hooks |

---

## Deployment Targets

| Environment | Platform | Database | Notes |
|-------------|----------|----------|-------|
| Local | CLI + FastAPI | SQLite | Development |
| Staging | Render | PostgreSQL | Testing |
| Production | Render | PostgreSQL | Main deploy |
| Dashboard | Vercel | - | Phase 4, separate repo |

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2025-12-11 | Python over TypeScript | Better Claude SDK, Langfuse, ML ecosystem |
| 2025-12-11 | Repos separados over monorepo | Different stacks, cleaner context for Claude Code |
| 2025-12-11 | MCP for browser | Agent has direct tool access |
| 2025-12-11 | FastAPI over Django | Async-first, lighter weight |
| 2025-12-12 | Gmail OAuth Desktop App | CLI local use, no redirect URI needed |
| 2025-12-12 | Remove Rich spinners | Windows cp1252 encoding issues with Braille chars |
| 2025-12-12 | AWS Bedrock over direct API | No API key needed, uses existing AWS credentials |
| 2025-12-12 | BeautifulSoup for HTML preprocessing | Clean email text before parsing (172KB -> 1.5KB) |
| 2025-12-12 | Brace-matching JSON extraction | LLM sometimes adds text after JSON object |
