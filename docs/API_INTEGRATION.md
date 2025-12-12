# API Integration Guide

> Last Updated: 2025-12-11
> Claude SDK Version: anthropic ^0.40.0
> Langfuse Version: langfuse ^2.54.0

## Overview

This document covers integration patterns for:
1. Anthropic Claude SDK
2. Langfuse observability
3. MCP browser automation

---

## Claude SDK Integration

### Installation

```bash
poetry add anthropic
```

### Environment Configuration

```env
ANTHROPIC_API_KEY=sk-ant-...
```

### Basic Client Setup

```python
# src/integrations/claude/client.py
from anthropic import Anthropic

def get_claude_client(api_key: str | None = None) -> Anthropic:
    """Get Claude client with optional user-provided API key."""
    return Anthropic(api_key=api_key)
```

### User-Provided API Key Pattern

```python
# src/api/dependencies.py
from fastapi import Header, HTTPException
from anthropic import Anthropic

async def get_claude_client(
    x_anthropic_api_key: str | None = Header(None),
) -> Anthropic:
    """Support user-provided API key via header."""
    import os
    api_key = x_anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(401, "Anthropic API key required")
    return Anthropic(api_key=api_key)
```

### Agent Implementation Pattern

```python
from anthropic import Anthropic
from pydantic import BaseModel

class CVAdapterOutput(BaseModel):
    adapted_cv: str
    match_score: int
    changes_made: list[str]

async def adapt_cv(
    client: Anthropic,
    base_cv: str,
    job_description: str,
) -> CVAdapterOutput:
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": f"""Adapt this CV for the job.

CV:
{base_cv}

Job Description:
{job_description}

Return JSON with: adapted_cv, match_score (0-100), changes_made (list)"""
        }]
    )

    # Parse response
    return CVAdapterOutput.model_validate_json(response.content[0].text)
```

---

## Langfuse Integration

### Installation

```bash
poetry add langfuse
```

### Environment Configuration

```env
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

### Basic Setup

```python
# src/integrations/langfuse/tracing.py
from langfuse import Langfuse

langfuse = Langfuse()

def get_langfuse() -> Langfuse:
    return langfuse
```

### Tracing Pattern

```python
from langfuse.decorators import observe

@observe()
async def adapt_cv(base_cv: str, job_description: str) -> CVAdapterOutput:
    # Function is automatically traced
    ...
```

### Generation Tracking

```python
from langfuse.decorators import observe, langfuse_context

@observe(as_type="generation")
async def call_claude(prompt: str) -> str:
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    # Update trace with usage
    langfuse_context.update_current_observation(
        usage={
            "input": response.usage.input_tokens,
            "output": response.usage.output_tokens,
        }
    )

    return response.content[0].text
```

---

## MCP Browser Integration

### Configuration

```json
// .claude/mcp.json
{
  "mcpServers": {
    "chrome": {
      "command": "npx",
      "args": ["@anthropic/chrome-devtools-mcp"],
      "transport": "stdio"
    }
  }
}
```

### Browser Client Abstraction

```python
# src/mcp/browser_client.py
from mcp import ClientSession

class BrowserClient:
    def __init__(self, session: ClientSession):
        self.session = session

    async def navigate(self, url: str) -> None:
        await self.session.call_tool("navigate", {"url": url})

    async def fill(self, selector: str, value: str) -> None:
        await self.session.call_tool("fill", {
            "selector": selector,
            "value": value
        })

    async def click(self, selector: str) -> None:
        await self.session.call_tool("click", {"selector": selector})

    async def screenshot(self) -> bytes:
        result = await self.session.call_tool("screenshot", {})
        return result.content
```

---

## Error Handling

```python
from anthropic import APIError, RateLimitError

async def safe_claude_call(client: Anthropic, prompt: str) -> str:
    try:
        response = client.messages.create(...)
        return response.content[0].text
    except RateLimitError:
        # Implement backoff
        await asyncio.sleep(60)
        return await safe_claude_call(client, prompt)
    except APIError as e:
        logger.error(f"Claude API error: {e}")
        raise
```

---

## Cost Tracking

```python
MODEL_COSTS = {
    "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
    "claude-opus-4-20250514": {"input": 0.015, "output": 0.075},
}

def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = MODEL_COSTS.get(model, {"input": 0, "output": 0})
    return (input_tokens / 1000 * rates["input"]) + (output_tokens / 1000 * rates["output"])
```
