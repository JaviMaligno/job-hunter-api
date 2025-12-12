"""Claude SDK client wrapper with observability - supports both Anthropic API and AWS Bedrock."""

from typing import Any, Union

from anthropic import Anthropic, AnthropicBedrock
from langfuse.decorators import langfuse_context, observe

from src.config import settings

# Type alias for client types
ClaudeClient = Union[Anthropic, AnthropicBedrock]


def get_claude_client(api_key: str | None = None) -> ClaudeClient:
    """
    Get Claude client instance - Bedrock or direct Anthropic API.

    Args:
        api_key: Optional API key (only used for direct Anthropic, ignored for Bedrock).

    Returns:
        Configured client (AnthropicBedrock if BEDROCK_ENABLED, else Anthropic).

    Raises:
        ValueError: If no API key is available and Bedrock is not enabled.
    """
    # Use AWS Bedrock if enabled
    if settings.bedrock_enabled:
        return AnthropicBedrock(
            aws_region=settings.bedrock_region,
            # Uses AWS credentials from environment/~/.aws/credentials
        )

    # Otherwise use direct Anthropic API
    key = api_key or settings.anthropic_api_key
    if not key:
        raise ValueError(
            "Anthropic API key is required when Bedrock is not enabled. "
            "Set ANTHROPIC_API_KEY environment variable or enable BEDROCK_ENABLED=true."
        )
    return Anthropic(api_key=key)


def get_model_id() -> str:
    """Get the appropriate model ID based on configuration."""
    if settings.bedrock_enabled:
        return settings.bedrock_model_id
    return "claude-sonnet-4-20250514"


@observe(as_type="generation")
async def call_claude(
    client: ClaudeClient,
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    **kwargs: Any,
) -> str:
    """
    Call Claude API with observability tracking.

    Args:
        client: Anthropic or AnthropicBedrock client instance.
        prompt: User message prompt.
        system: Optional system prompt.
        model: Model to use (auto-detected from settings if None).
        max_tokens: Maximum tokens in response.
        temperature: Sampling temperature.
        **kwargs: Additional parameters for the API.

    Returns:
        Text content from Claude's response.
    """
    # Auto-detect model from settings if not specified
    if model is None:
        model = get_model_id()

    messages = [{"role": "user", "content": prompt}]

    create_kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
        **kwargs,
    }

    if system:
        create_kwargs["system"] = system

    response = client.messages.create(**create_kwargs)

    # Update Langfuse trace with usage info
    if response.usage:
        langfuse_context.update_current_observation(
            model=model,
            usage={
                "input": response.usage.input_tokens,
                "output": response.usage.output_tokens,
            },
            model_parameters={
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )

    # Extract text from response
    text_content = ""
    for block in response.content:
        if block.type == "text":
            text_content += block.text

    return text_content


@observe(as_type="generation")
async def call_claude_with_tools(
    client: ClaudeClient,
    prompt: str,
    tools: list[dict[str, Any]],
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 4096,
    **kwargs: Any,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Call Claude API with tool use.

    Args:
        client: Anthropic or AnthropicBedrock client instance.
        prompt: User message prompt.
        tools: List of tool definitions.
        system: Optional system prompt.
        model: Model to use (auto-detected from settings if None).
        max_tokens: Maximum tokens in response.
        **kwargs: Additional parameters.

    Returns:
        Tuple of (text_response, tool_calls).
    """
    # Auto-detect model from settings if not specified
    if model is None:
        model = get_model_id()

    messages = [{"role": "user", "content": prompt}]

    create_kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
        "tools": tools,
        **kwargs,
    }

    if system:
        create_kwargs["system"] = system

    response = client.messages.create(**create_kwargs)

    # Update Langfuse trace
    if response.usage:
        langfuse_context.update_current_observation(
            model=model,
            usage={
                "input": response.usage.input_tokens,
                "output": response.usage.output_tokens,
            },
        )

    # Extract text and tool calls
    text_content = ""
    tool_calls = []

    for block in response.content:
        if block.type == "text":
            text_content += block.text
        elif block.type == "tool_use":
            tool_calls.append(
                {
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }
            )

    return text_content, tool_calls


# Cost calculation utilities
MODEL_COSTS = {
    "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
    "claude-opus-4-20250514": {"input": 0.015, "output": 0.075},
    "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
    "claude-3-5-haiku-20241022": {"input": 0.001, "output": 0.005},
    # Bedrock models (costs may vary)
    "eu.anthropic.claude-sonnet-4-5-20250929-v1:0": {"input": 0.003, "output": 0.015},
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    Calculate cost for a Claude API call.

    Args:
        model: Model identifier.
        input_tokens: Number of input tokens.
        output_tokens: Number of output tokens.

    Returns:
        Estimated cost in USD.
    """
    rates = MODEL_COSTS.get(model, {"input": 0.003, "output": 0.015})
    return (input_tokens / 1000 * rates["input"]) + (output_tokens / 1000 * rates["output"])
