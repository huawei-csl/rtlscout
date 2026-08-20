"""The P1 prompt must not advertise optimization features whose flag is off.

Measured motivation: with both flags off the spire prompt still named the
decorators (via the inlined README + hints.md) but never said how to import them,
so the agent guessed -- 69 decorator tokens across 9/18 phase-1 runs and 14
evaluations destroyed by bad imports. See
artifacts/pdpu_run/analysis/p1_convergence/README.md.
"""
from pathlib import Path

import pytest

from core.prompts import (_GATED_TOKENS, _scrub_gated_features,
                          build_spirehdl_system_prompt)

FLAGS = ("abc_optimize", "flowy_optimize", "arith_autoconfig", "fsm_optimize")


def _prompt(**flags):
    return build_spirehdl_system_prompt("SPEC", "area", **flags)


@pytest.mark.parametrize("token,flag", sorted(_GATED_TOKENS.items()))
def test_absent_when_all_flags_off(token, flag):
    """Phase 1: every flag off -> no feature is named anywhere in the prompt."""
    assert token not in _prompt()


@pytest.mark.parametrize("flag", FLAGS)
def test_present_when_its_flag_is_on(flag):
    """Enabling a flag must restore its own tokens (gating, not deletion)."""
    p = _prompt(**{flag: True})
    for token, owner in _GATED_TOKENS.items():
        if owner == flag:
            assert token in p, f"{token} missing with {flag}=True"


def test_scrub_is_identity_when_all_flags_on():
    """With every flag on the scrubber must not touch the markdown at all."""
    md = Path("core/spirehdl_readme.md").read_text()
    assert _scrub_gated_features(md, **{f: True for f in FLAGS}) == md


def test_scrub_removes_only_the_gated_blocks():
    """Scrubbing drops the feature blocks and nothing else."""
    md = Path("core/spirehdl_readme.md").read_text()
    out = _scrub_gated_features(md)
    assert not any(t in out for t in _GATED_TOKENS)
    kept = [l for l in md.splitlines() if l in out.splitlines()]
    assert len(kept) > 0.9 * len(md.splitlines())


def test_prompt_does_not_recommend_simplify():
    """`simplify=True` destroyed 32 of 111 evals that used it (29 %) and never
    produced a campaign winner, so the prompt must not suggest it."""
    p = _prompt()
    assert "Pass `simplify=True`" not in p
    assert "Do **not** pass `simplify=True`" in p
