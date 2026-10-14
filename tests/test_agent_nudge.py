"""The reminder after a reply without a tool call names an empty reply and its likely cause (the completion cap)."""
from types import SimpleNamespace

from rtlscout.agent import RTLAgent


def _nudge(content, finish_reason, max_tokens=65536):
    fake_agent = SimpleNamespace(client=SimpleNamespace(max_tokens=max_tokens), max_steps=60)
    return RTLAgent._nudge(fake_agent, 7, SimpleNamespace(content=content, finish_reason=finish_reason))


def test_text_without_tool_call_gets_the_plain_reminder():
    assert _nudge("Let me think about the adder tree.", "stop") == \
        "[Step 7/60] Please use a tool. The run ends automatically at the step limit."


def test_empty_reply_cut_at_the_cap_names_the_limit():
    assert _nudge(None, "length") == ("[Step 7/60] Empty reply, the completion limit of 65,536 tokens (reasoning included) "
                                      "was exceeded. Reason more briefly, then use a tool. The run ends automatically at the "
                                      "step limit.")
    assert "the completion limit (reasoning included) was exceeded" in _nudge("", "length", max_tokens=None)


def test_empty_reply_without_a_known_reason_is_hedged():
    assert "Empty reply, possibly the completion limit (reasoning included) was exceeded." in _nudge("  ", None)
