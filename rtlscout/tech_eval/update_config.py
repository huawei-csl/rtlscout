#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(
            "Usage: update_config.py <config_path> <design_nickname> <design_name>"
        )

    config_path = Path(sys.argv[1])
    design_nickname = sys.argv[2]
    design_name = sys.argv[3]

    if not config_path.exists():
        raise SystemExit(f"config path not found: {config_path}")

    lines = config_path.read_text().splitlines()
    nick_found = False
    name_found = False
    new_lines: list[str] = []

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("export DESIGN_NICKNAME"):
            new_lines.append(f"export DESIGN_NICKNAME        = {design_nickname}")
            nick_found = True
        elif stripped.startswith("export DESIGN_NAME"):
            new_lines.append(f"export DESIGN_NAME            = {design_name}")
            name_found = True
        elif stripped.startswith("export VERILOG_TOP_PARAMS"):
            continue
        else:
            new_lines.append(line)

    if not nick_found:
        new_lines.append(f"export DESIGN_NICKNAME        = {design_nickname}")
    if not name_found:
        new_lines.append(f"export DESIGN_NAME            = {design_name}")

    config_path.write_text("\n".join(new_lines) + "\n")


if __name__ == "__main__":
    main()
