"""LLM client abstraction: provider-agnostic interface for chat completions."""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from openai import OpenAI


@dataclass
class ToolCall:
    """A single tool/function call from the model."""
    id: str
    name: str
    arguments: str  # JSON string


@dataclass
class TokenUsage:
    """Token usage breakdown for a single API call."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def total_input(self) -> int:
        return self.input_tokens + self.cache_creation_input_tokens + self.cache_read_input_tokens

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_creation_input_tokens=self.cache_creation_input_tokens + other.cache_creation_input_tokens,
            cache_read_input_tokens=self.cache_read_input_tokens + other.cache_read_input_tokens,
        )

    def summary(self) -> str:
        parts = [f"input={self.input_tokens}"]
        if self.cache_creation_input_tokens:
            parts.append(f"cache_write={self.cache_creation_input_tokens}")
        if self.cache_read_input_tokens:
            parts.append(f"cache_read={self.cache_read_input_tokens}")
        parts.append(f"output={self.output_tokens}")
        parts.append(f"total_in={self.total_input}")
        return " | ".join(parts)


@dataclass
class ChatResponse:
    """Standardized response from any LLM provider."""
    content: Optional[str]
    tool_calls: List[ToolCall] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)


class LLMClient(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto",
    ) -> ChatResponse:
        """Send a chat completion request and return a standardized response."""
        ...


class DeepInfraClient(LLMClient):
    """OpenAI-compatible client for DeepInfra."""

    DEEPINFRA_BASE_URL = "https://api.deepinfra.com/v1/openai"

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = DEEPINFRA_BASE_URL,
    ):
        super().__init__(model)
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto",
    ) -> ChatResponse:
        kwargs = dict(model=self.model, messages=messages)
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        response = self._client.chat.completions.create(**kwargs)
        msg = response.choices[0].message

        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                ))

        usage = TokenUsage()
        if response.usage:
            usage.input_tokens = response.usage.prompt_tokens or 0
            usage.output_tokens = response.usage.completion_tokens or 0

        return ChatResponse(content=msg.content, tool_calls=tool_calls, usage=usage)


class OpenRouterClient(LLMClient):
    """OpenAI-compatible client for OpenRouter."""

    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = OPENROUTER_BASE_URL,
    ):
        super().__init__(model)
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={
                "HTTP-Referer": "https://github.com/huawei-csl/rtlscout",
                "X-OpenRouter-Title": "core",
            },
        )

    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto",
    ) -> ChatResponse:
        kwargs = dict(model=self.model, messages=messages)
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        response = self._client.chat.completions.create(**kwargs)
        msg = response.choices[0].message

        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                ))

        usage = TokenUsage()
        if response.usage:
            usage.input_tokens = response.usage.prompt_tokens or 0
            usage.output_tokens = response.usage.completion_tokens or 0

        return ChatResponse(content=msg.content, tool_calls=tool_calls, usage=usage)


class AnthropicClient(LLMClient):
    """Anthropic Claude client with OpenAI-to-Claude message translation and prompt caching."""

    def __init__(self, model: str, api_key: str, prompt_caching: bool = True):
        super().__init__(model)
        self.prompt_caching = prompt_caching
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package is required for AnthropicClient. "
                "Install it with: pip install anthropic"
            )
        self._client = anthropic.Anthropic(api_key=api_key)

    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto",
    ) -> ChatResponse:
        system, converted_messages = self._convert_messages(messages)
        converted_tools = self._convert_tools(tools)

        if self.prompt_caching:
            self._inject_cache_breakpoints(system, converted_tools, converted_messages)

        kwargs = dict(
            model=self.model,
            max_tokens=16384,
            system=system,
            messages=converted_messages,
        )
        if converted_tools:
            kwargs["tools"] = converted_tools
            kwargs["tool_choice"] = (
                {"type": tool_choice} if tool_choice == "auto" else {"type": "any"}
            )
        response = self._client.messages.create(**kwargs)

        return self._convert_response(response)

    @staticmethod
    def _convert_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert OpenAI tool format to Anthropic tool format."""
        if not tools:
            return []
        converted = []
        for tool in tools:
            func = tool["function"]
            converted.append({
                "name": func["name"],
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
            })
        return converted

    @staticmethod
    def _convert_messages(
        messages: List[Dict[str, Any]],
    ) -> tuple:
        """Convert OpenAI-format messages to Anthropic format.

        Returns (system_blocks, messages) where system is a list of content
        blocks and messages are converted to Anthropic format.
        """
        system = []
        converted = []

        for msg in messages:
            role = msg["role"]

            if role == "system":
                text = msg["content"] or ""
                system.append({"type": "text", "text": text})
                continue

            if role == "user":
                converted.append({"role": "user", "content": msg["content"]})
                continue

            if role == "assistant":
                content_blocks = []
                # Add text content if present
                if msg.get("content"):
                    content_blocks.append({"type": "text", "text": msg["content"]})
                # Convert tool_calls to tool_use blocks
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        func = tc["function"]
                        try:
                            input_data = json.loads(func["arguments"])
                        except (json.JSONDecodeError, TypeError):
                            input_data = {}
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": func["name"],
                            "input": input_data,
                        })
                if content_blocks:
                    converted.append({"role": "assistant", "content": content_blocks})
                continue

            if role == "tool":
                # Tool results need to be grouped into a single user message
                # with tool_result content blocks. Check if the last converted
                # message is already a user message with tool_result blocks.
                tool_result_block = {
                    "type": "tool_result",
                    "tool_use_id": msg["tool_call_id"],
                    "content": msg["content"] or "",
                }
                if (
                    converted
                    and converted[-1]["role"] == "user"
                    and isinstance(converted[-1]["content"], list)
                    and converted[-1]["content"]
                    and converted[-1]["content"][0].get("type") == "tool_result"
                ):
                    converted[-1]["content"].append(tool_result_block)
                else:
                    converted.append({
                        "role": "user",
                        "content": [tool_result_block],
                    })
                continue

        return system, converted

    @staticmethod
    def _inject_cache_breakpoints(
        system: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        messages: List[Dict[str, Any]],
    ) -> None:
        """Add cache_control breakpoints to maximize prompt caching.

        Strategy (up to 4 breakpoints allowed):
        1. Last tool definition — tools are static across all steps
        2. Last system block — system prompt is static across all steps
        3. Last user/tool_result message — caches conversation history so far
        """
        # Breakpoint 1: last tool
        if tools:
            tools[-1]["cache_control"] = {"type": "ephemeral"}

        # Breakpoint 2: last system block
        if system:
            system[-1]["cache_control"] = {"type": "ephemeral"}

        # Breakpoint 3: last message in conversation (the most recent user turn)
        # Walk backwards to find the last user message and mark its last content block.
        for msg in reversed(messages):
            if msg["role"] == "user":
                content = msg["content"]
                if isinstance(content, list) and content:
                    content[-1]["cache_control"] = {"type": "ephemeral"}
                elif isinstance(content, str):
                    # Convert string content to block format so we can add cache_control
                    msg["content"] = [
                        {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
                    ]
                break

    @staticmethod
    def _convert_response(response) -> ChatResponse:
        """Convert Anthropic response to standardized ChatResponse."""
        content_text = None
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content_text = block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=json.dumps(block.input),
                ))

        usage = TokenUsage(
            input_tokens=response.usage.input_tokens or 0,
            output_tokens=response.usage.output_tokens or 0,
            cache_creation_input_tokens=getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
            cache_read_input_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
        )

        return ChatResponse(content=content_text, tool_calls=tool_calls, usage=usage)
