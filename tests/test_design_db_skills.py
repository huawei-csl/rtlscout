"""K1 tests: the design-DB skill pack + provisioning module (skill/subagent integration).

Layout rules matter: opencode discovers `.opencode/skills/**/SKILL.md` and requires the
frontmatter `name` to equal the directory name (NameMismatchError otherwise).
"""
import stat

from core.design_db_skills import (SKILL_NAMES, SKILLS_SRC, design_db_subagent_entries,
                                   provision_design_db_skills, render_design_db_agents_section)


def _frontmatter(text: str) -> dict:
    assert text.startswith("---\n"), "SKILL.md must start with YAML frontmatter"
    block = text.split("---", 2)[1]
    fields = {}
    for line in block.strip().splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def test_skill_pack_layout():
    assert SKILLS_SRC.is_dir()
    dirs = sorted(p.name for p in SKILLS_SRC.iterdir() if p.is_dir())
    assert dirs == sorted(SKILL_NAMES)
    for name in SKILL_NAMES:
        md = SKILLS_SRC / name / "SKILL.md"
        fm = _frontmatter(md.read_text())
        assert fm["name"] == name, f"{md}: frontmatter name must equal the directory name"
        assert len(fm.get("description", "")) > 20


def test_provision_into_workspace(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    dest = provision_design_db_skills(ws)
    assert dest == ws / ".opencode" / "skills"
    for name in SKILL_NAMES:
        assert (dest / name / "SKILL.md").exists()
    wrapper = dest / "design-db-score" / "scripts" / "db-score"
    assert wrapper.stat().st_mode & stat.S_IXUSR, "db-score wrapper must be executable"
    text = wrapper.read_text()
    assert "rtlscout_cli.py db-score" in text and '"$@"' in text
    provision_design_db_skills(ws)                       # idempotent re-provision
    assert (dest / "design-db-inspect" / "SKILL.md").exists()


def test_subagent_entries_shape():
    perms = {"bash": "allow", "task": "allow", "skill": "allow"}
    entries = design_db_subagent_entries("openrouter/z-ai/glm-4.6", perms)
    assert set(entries) == {"rtl-subcircuit", "rtl-dv-prep"}
    for name, e in entries.items():
        assert e["mode"] == "subagent" and e["hidden"] is True
        assert e["tools"]["task"] is False                # structural depth cap
        assert e["permission"]["task"] == "deny"
        assert e["model"] == "openrouter/z-ai/glm-4.6"
        assert "work/<spec_key>/" in e["prompt"]
    assert perms["task"] == "allow", "the primary agent's perms dict must not be mutated"
    assert "spire db insert" in entries["rtl-subcircuit"]["prompt"]
    assert "--check" in entries["rtl-dv-prep"]["prompt"]
    assert "Do NOT freeze" in entries["rtl-dv-prep"]["prompt"]


def test_agents_md_section():
    section = render_design_db_agents_section()
    for name in SKILL_NAMES:
        assert name in section
    assert "spire db insert" in section and "task tool" in section
