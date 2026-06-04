"""Fake LLM provider for integration testing (no API calls)."""

import json
from typing import Any, Dict, List, Optional

from core.llm_client import ChatResponse, LLMClient, TokenUsage, ToolCall

_SCRIPT_REGISTRY: Dict[str, List[ChatResponse]] = {}


def register_fake_script(name: str, script: List[ChatResponse]):
    _SCRIPT_REGISTRY[name] = script


def build_fake_client(model: str) -> "FakeLLMClient":
    if model not in _SCRIPT_REGISTRY:
        raise ValueError(f"No fake script registered for model '{model}'. "
                         f"Available: {list(_SCRIPT_REGISTRY.keys())}")
    return FakeLLMClient(model=model, script=list(_SCRIPT_REGISTRY[model]))


class FakeLLMClient(LLMClient):
    """Deterministic LLM client that returns pre-scripted responses."""

    def __init__(self, model: str, script: List[ChatResponse]):
        super().__init__(model)
        self._script = script
        self._call_index = 0

    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
    ) -> ChatResponse:
        if self._call_index < len(self._script):
            response = self._script[self._call_index]
            self._call_index += 1
            return response
        return ChatResponse(content="Fake summary.", tool_calls=[], usage=TokenUsage())


# ---------------------------------------------------------------------------
# Pre-registered scripts
# ---------------------------------------------------------------------------

_SIMPLE_ADDER_VERILOG = """\
module adder(input [7:0] a, b, output [7:0] sum);
  assign sum = a + b;
endmodule
"""

register_fake_script("simple_adder_pass", [
    ChatResponse(
        content="Creating adder design.",
        tool_calls=[ToolCall(
            id="fake_1",
            name="create_file",
            arguments=json.dumps({"filename": "design.sv", "content": _SIMPLE_ADDER_VERILOG}),
        )],
        usage=TokenUsage(input_tokens=10, output_tokens=10),
    ),
    ChatResponse(
        content="Evaluating.",
        tool_calls=[ToolCall(
            id="fake_2",
            name="run_evaluation",
            arguments=json.dumps({"filename": "design.sv"}),
        )],
        usage=TokenUsage(input_tokens=10, output_tokens=10),
    ),
    ChatResponse(
        content="Done.",
        tool_calls=[ToolCall(
            id="fake_3",
            name="done",
            arguments=json.dumps({"message": "Complete."}),
        )],
        usage=TokenUsage(input_tokens=10, output_tokens=10),
    ),
])

_SIMPLE_ADDER_SPIREHDL = """\
from spirehdl.spirehdl_module import Module
from spirehdl.spirehdl import UInt

m = Module("adder", with_clock=False, with_reset=False)
a = m.input(UInt(8), "a")
b = m.input(UInt(8), "b")
s = m.output(UInt(8), "sum")
s <<= (a + b)[0:8]
m.to_verilog_file("design.v")
"""

register_fake_script("simple_adder_spirehdl_pass", [
    ChatResponse(
        content="Creating SpireHDL adder design.",
        tool_calls=[ToolCall(
            id="fake_1",
            name="create_file",
            arguments=json.dumps({"filename": "design.py", "content": _SIMPLE_ADDER_SPIREHDL}),
        )],
        usage=TokenUsage(input_tokens=10, output_tokens=10),
    ),
    ChatResponse(
        content="Evaluating.",
        tool_calls=[ToolCall(
            id="fake_2",
            name="run_evaluation",
            arguments=json.dumps({"filename": "design.py"}),
        )],
        usage=TokenUsage(input_tokens=10, output_tokens=10),
    ),
    ChatResponse(
        content="Done.",
        tool_calls=[ToolCall(
            id="fake_3",
            name="done",
            arguments=json.dumps({"message": "Complete."}),
        )],
        usage=TokenUsage(input_tokens=10, output_tokens=10),
    ),
])
