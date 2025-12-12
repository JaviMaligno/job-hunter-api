"""Base agent class with Langfuse observability."""

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from langfuse.decorators import langfuse_context, observe
from pydantic import BaseModel

from src.integrations.claude.client import ClaudeClient, get_claude_client, get_model_id

# Type variable for agent output
T = TypeVar("T", bound=BaseModel)


class BaseAgent(ABC, Generic[T]):
    """
    Base class for all AI agents with Langfuse observability.

    All agents should:
    1. Inherit from this class
    2. Define `name` and `system_prompt` properties
    3. Implement `_execute` method
    4. Define input/output Pydantic models
    """

    def __init__(
        self,
        claude_api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ):
        """
        Initialize the agent.

        Args:
            claude_api_key: Optional API key (uses env var if not provided, ignored for Bedrock).
            model: Claude model to use (auto-detected from settings if None).
            max_tokens: Maximum tokens for response.
            temperature: Sampling temperature.
        """
        self.client: ClaudeClient = get_claude_client(claude_api_key)
        self.model = model or get_model_id()
        self.max_tokens = max_tokens
        self.temperature = temperature

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent name for tracing and logging."""
        pass

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """System prompt defining the agent's behavior."""
        pass

    @observe()
    async def run(self, input_data: Any, **kwargs: Any) -> T:
        """
        Execute the agent with full observability.

        Args:
            input_data: Input data for the agent (typically a Pydantic model).
            **kwargs: Additional parameters.

        Returns:
            Agent output (Pydantic model).
        """
        # Update trace context
        langfuse_context.update_current_trace(
            name=f"{self.name}-execution",
            metadata={
                "model": self.model,
                "max_tokens": self.max_tokens,
            },
        )

        # Serialize input for logging
        input_dict = input_data.model_dump() if hasattr(input_data, "model_dump") else input_data
        langfuse_context.update_current_observation(
            input=input_dict,
        )

        try:
            result = await self._execute(input_data, **kwargs)

            # Log output
            output_dict = result.model_dump() if hasattr(result, "model_dump") else result
            langfuse_context.update_current_observation(
                output=output_dict,
            )

            return result

        except Exception as e:
            langfuse_context.update_current_observation(
                level="ERROR",
                status_message=str(e),
            )
            raise

    @abstractmethod
    async def _execute(self, input_data: Any, **kwargs: Any) -> T:
        """
        Implementation-specific execution logic.

        Args:
            input_data: Input data for the agent.
            **kwargs: Additional parameters.

        Returns:
            Agent output.
        """
        pass

    async def _call_claude(
        self,
        prompt: str,
        system: str | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Make a Claude API call with tracing.

        Args:
            prompt: User prompt.
            system: Optional system override (uses agent's system_prompt by default).
            **kwargs: Additional API parameters.

        Returns:
            Text response from Claude.
        """
        messages = [{"role": "user", "content": prompt}]

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system or self.system_prompt,
            messages=messages,
            **kwargs,
        )

        # Update trace with usage
        if response.usage:
            langfuse_context.update_current_observation(
                usage={
                    "input": response.usage.input_tokens,
                    "output": response.usage.output_tokens,
                },
                model=self.model,
            )

        # Extract text content
        text_content = ""
        for block in response.content:
            if block.type == "text":
                text_content += block.text

        return text_content

    async def _call_claude_json(
        self,
        prompt: str,
        output_model: type[BaseModel],
        system: str | None = None,
        **kwargs: Any,
    ) -> BaseModel:
        """
        Make a Claude API call expecting JSON output.

        Args:
            prompt: User prompt (should instruct JSON output).
            output_model: Pydantic model for parsing response.
            system: Optional system override.
            **kwargs: Additional API parameters.

        Returns:
            Parsed Pydantic model.
        """
        # Add JSON instruction to prompt
        json_prompt = f"""{prompt}

IMPORTANT: Return your response as valid JSON that matches this schema:
{output_model.model_json_schema()}

Return ONLY the JSON object, no markdown code blocks or additional text."""

        response_text = await self._call_claude(json_prompt, system=system, **kwargs)

        # Clean up response (remove potential markdown and trailing text)
        clean_text = response_text.strip()

        # Remove markdown code blocks
        if clean_text.startswith("```"):
            lines = clean_text.split("\n")
            clean_text = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])
            clean_text = clean_text.strip()

        # Extract JSON object - find the matching braces
        if clean_text.startswith("{"):
            brace_count = 0
            end_pos = 0
            for i, char in enumerate(clean_text):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end_pos = i + 1
                        break
            if end_pos > 0:
                clean_text = clean_text[:end_pos]

        return output_model.model_validate_json(clean_text)
