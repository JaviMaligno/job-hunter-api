# Job Application Automation Guide

## Overview

This system automates job applications using a hybrid approach:

1. **Primary**: Gemini 2.5 + Chrome DevTools MCP (automatic)
2. **Secondary**: Claude FormFillerAgent (fallback)
3. **Manual**: Claude Code CLI (human-in-the-loop)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend Dashboard                        │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Kanban  │  │  Automation  │  │  Interventions Feed  │  │
│  │  Board   │  │    Center    │  │     (WebSocket)      │  │
│  └──────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                 /api/applications/v2                  │  │
│  │  • start      - Start with agent selection           │  │
│  │  • sessions   - List/manage sessions                 │  │
│  │  • resume     - Resume paused sessions               │  │
│  │  • interventions - Manage blockers                   │  │
│  └──────────────────────────────────────────────────────┘  │
│                              │                               │
│  ┌───────────────┐  ┌───────────────┐  ┌────────────────┐  │
│  │    Gemini     │  │    Claude     │  │  Intervention  │  │
│  │  Orchestrator │  │  FormFiller   │  │    Manager     │  │
│  └───────────────┘  └───────────────┘  └────────────────┘  │
│           │                 │                  │            │
│           └─────────────────┴──────────────────┘            │
│                              │                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Chrome DevTools MCP                      │  │
│  │  • Navigation  • Form filling  • Screenshots          │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   External Services                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │   2captcha   │  │   Browser    │  │  Claude Code CLI │  │
│  │   (auto)     │  │   (Chrome)   │  │    (manual)      │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Agent Selection

### Gemini (Default)
```python
# Uses Gemini 2.5 Pro/Flash with Chrome MCP
request = {
    "job_url": "https://...",
    "user_data": {...},
    "cv_content": "...",
    "agent": "gemini",  # Default
    "auto_solve_captcha": True
}
```

### Claude
```python
# Uses Claude FormFillerAgent
request = {
    "agent": "claude"
}
```

### Hybrid
```python
# Gemini with Claude fallback
request = {
    "agent": "hybrid"  # Tries Gemini, falls back to Claude
}
```

## Intervention Flow

When automation encounters a blocker:

1. **Detection**: Agent detects CAPTCHA, login, or complex form
2. **Auto-solve Attempt**: If 2captcha is configured, tries automatic solving
3. **Intervention Created**: If auto-solve fails, creates intervention
4. **WebSocket Notification**: Dashboard receives real-time alert
5. **Manual Resolution**: User resolves via dashboard or Claude Code CLI
6. **Resume**: Automation continues from where it stopped

### Intervention Types

| Type | Description | Auto-solvable |
|------|-------------|---------------|
| `captcha` | Turnstile, hCaptcha, reCAPTCHA | Yes (2captcha) |
| `login_required` | Site requires login | No |
| `file_upload` | Complex file upload needed | No |
| `custom_question` | Unusual form questions | No |
| `multi_step_form` | Complex multi-page form | Partial |
| `review_before_submit` | Ready for final review | No |
| `error` | Unexpected error occurred | No |

## Claude Code CLI Fallback

For blockers that can't be auto-resolved:

```bash
# Resolve an intervention
poetry run python scripts/claude_code_fallback.py --intervention <id>

# Resume a session
poetry run python scripts/claude_code_fallback.py --session <id>

# Direct URL
poetry run python scripts/claude_code_fallback.py --url <url> --task "Fill application"

# Generate context only (don't launch)
poetry run python scripts/claude_code_fallback.py --intervention <id> --no-launch

# Auto-resolve after completion
poetry run python scripts/claude_code_fallback.py --intervention <id> --resolve-after
```

## Session Persistence

Sessions are stored in `data/sessions/*.json` and can be:

- **Resumed**: Continue from where automation stopped
- **Deleted**: Remove session and its data
- **Viewed**: See full session state and progress

### Session States

| Status | Description | Can Resume |
|--------|-------------|------------|
| `pending` | Not started | No |
| `in_progress` | Currently running | No |
| `paused` | Stopped by user/system | Yes |
| `needs_intervention` | Blocked, needs help | Yes |
| `submitted` | Successfully completed | No |
| `failed` | Error occurred | No |
| `cancelled` | User cancelled | No |

## WebSocket Events

Connect to `/api/applications/v2/ws/interventions` for real-time updates:

```javascript
const ws = new WebSocket('ws://localhost:8000/api/applications/v2/ws/interventions');

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  switch (msg.type) {
    case 'initial_state':
      // Initial list of pending interventions
      break;
    case 'intervention':
      // New intervention created
      break;
    case 'intervention_resolved':
      // Intervention was resolved
      break;
  }
};

// Request refresh
ws.send('refresh');

// Keepalive
ws.send('ping');
```

## Configuration

### Environment Variables

```env
# Gemini API
GEMINI_API_KEY=your_key

# 2captcha (optional, for auto-solving)
TWOCAPTCHA_API_KEY=your_key

# Chrome MCP
# Make sure Chrome DevTools MCP server is running on port 9222
```

### Rate Limits

- Default: 10 applications/day
- Auto mode: 5 applications/day
- Configurable in `.env`

## Troubleshooting

### Gemini Quota Exceeded
The system automatically falls back to Gemini Flash. Set `gemini_model` to override:
```python
request = {"gemini_model": "gemini-2.5-flash"}
```

### Chrome MCP Not Connected
Ensure Chrome DevTools MCP server is running:
```bash
npx @anthropic-ai/mcp-server-chrome
```

### CAPTCHA Not Solving
1. Check 2captcha balance
2. Verify TWOCAPTCHA_API_KEY is set
3. Some CAPTCHAs require manual intervention

### Session Won't Resume
- Check if session file exists in `data/sessions/`
- Verify session status is `paused` or `needs_intervention`
- Ensure user data is complete in session
