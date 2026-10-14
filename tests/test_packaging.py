"""Packaging metadata that has to stay consistent by hand."""

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _name(requirement: str) -> str:
    return re.split(r"[<>=!~;\[ @]", requirement, maxsplit=1)[0].strip().lower()


def test_requirements_txt_lists_the_third_party_dependencies_of_the_package():
    """requirements.txt is what images bake ahead of time (.devcontainer/Dockerfile.opencode); spire-hdl is
    installed separately there, from the submodule."""
    declared = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["dependencies"]
    listed = [line.strip() for line in (REPO / "requirements.txt").read_text().splitlines() if line.strip()]
    assert sorted(map(_name, listed)) == sorted(n for n in map(_name, declared) if n != "spire-hdl")


def test_no_direct_url_dependencies():
    """Keeps the package uploadable to an index later."""
    project = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]
    extras = [r for group in project.get("optional-dependencies", {}).values() for r in group]
    assert not [r for r in project["dependencies"] + extras if "@" in r or "://" in r]
