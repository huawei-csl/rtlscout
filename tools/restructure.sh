#!/usr/bin/env bash
# Mechanical, repo-wide renames for the rtlscout packaging. One step per commit, nothing hand-edited:
#
#   tools/restructure.sh core        core/ -> rtlscout/, and every reference to it
#   tools/restructure.sh tech_eval   deps/tech_eval/src/tech_eval/ -> rtlscout/tech_eval/, and every module reference
#
# Run from the repo root. Idempotent: a second run changes nothing.
#
# A repo that only *uses* rtlscout (imports it, calls its modules, has no core/ of its own) converts its
# references with
#   RTLSCOUT_PKG_DIR=<converted checkout>/rtlscout bash <converted checkout>/tools/restructure.sh <step>
# The package directory is then only read for its module names; nothing is moved.
set -euo pipefail
export LC_ALL=C

SELF=tools/restructure.sh
PKG="${RTLSCOUT_PKG_DIR:-rtlscout}"
TEXT=('*.py' '*.md' '*.sh' '*.yml' '*.yaml' '*.toml' '*.json' '*.txt' '*.cfg'
      '*Dockerfile*' '*.dockerignore' '*.gitignore')

# Tracked text files under the given pathspecs that contain the (extended) regex, NUL-separated.
# Never this script, never the core/ compatibility shim.
files_with() {
  local re=$1; shift
  git grep -lzIE -e "$re" -- "$@" ":(exclude)$SELF" ':(exclude)core/__init__.py' || true
}

step_core() {
  if [ -z "${RTLSCOUT_PKG_DIR:-}" ] && [ -d core ] && [ ! -d rtlscout ]; then git mv core rtlscout; fi
  [ -d "$PKG" ] || { echo "error: no package directory at '$PKG'" >&2; exit 1; }

  # 1. import statements, wherever a line starts with one (Python files, code blocks in docs, heredocs)
  files_with '^[[:space:]]*(from|import)[[:space:]]+core(\.|[[:space:]]|$)' '*.py' '*.md' '*.sh' '*.yml' '*.yaml' \
    | xargs -0 -r sed -i -E \
      -e 's/^([[:space:]]*)from core(\.| import )/\1from rtlscout\2/' \
      -e 's/^([[:space:]]*)import core(\.|$| as )/\1import rtlscout\2/'

  # 2. dotted module references outside import statements: `python -m core.eval_store`, ["-m", "core.reeval"],
  #    patch("core.x"), assertions on "core.eval_store", prose. Not `<pkg>.core.<mod>` of another package.
  local mods
  mods=$(git -C "$PKG" ls-files '*.py' | grep -v / | sed 's/\.py$//' | grep -v '^__' | paste -sd'|')
  files_with "core\.(${mods}|\*)" "${TEXT[@]}" \
    | xargs -0 -r perl -pi -e "s/(?<![\w.\/-])core\.((?:${mods})\b|\*)/rtlscout.\$1/g"

  # 3. path references: core/<file or directory of the package>, and the bare directory `core/`
  local names
  names=$(git -C "$PKG" ls-files | cut -d/ -f1 | sort -u | grep -v '^__' \
            | sed -e 's/\.py$//' -e 's/\./\\./g' | paste -sd'|')
  files_with "core/(${names})" "${TEXT[@]}" \
    | xargs -0 -r perl -pi -e "s#(?<![\w.-])(?<!ppa_extract/)core/((?:${names})\b)#rtlscout/\$1#g"
  files_with '`core/`' "${TEXT[@]}" ':(exclude)*tech_eval/*' | xargs -0 -r sed -i 's#`core/`#`rtlscout/`#g'
  # ... and the directory as a quoted component of a path join: REPO / "core" / "agent.py", (d / "core").is_dir()
  files_with "/ *[\"']core[\"']" "${TEXT[@]}" ':(exclude)*tech_eval/*' \
    | xargs -0 -r sed -i -E "s#(/ *[\"'])core([\"'])#\\1rtlscout\\2#g"
}

step_tech_eval() {          # requires step_core to have run (the package directory must exist)
  [ -d "$PKG" ] || { echo "error: no package directory at '$PKG' (run the core step first)" >&2; exit 1; }
  if [ -z "${RTLSCOUT_PKG_DIR:-}" ] && [ -d deps/tech_eval/src/tech_eval ] && [ ! -d rtlscout/tech_eval ]; then
    git mv deps/tech_eval/src/tech_eval rtlscout/tech_eval
  fi

  # 1. the moved directory: as a path string (also abbreviated `deps/tech_eval/.../x.py`) and as a path join
  files_with 'deps/tech_eval/(src/tech_eval|\.\.\./)' "${TEXT[@]}" \
    | xargs -0 -r sed -i -E -e 's#deps/tech_eval/src/tech_eval#rtlscout/tech_eval#g' \
                            -e 's#deps/tech_eval/\.\.\./#rtlscout/tech_eval/.../#g'
  local q="[\"']" join
  join="${q}deps${q} */ *${q}tech_eval${q} */ *${q}src${q} */ *${q}tech_eval${q}"
  files_with "$join" '*.py' \
    | xargs -0 -r sed -i -E "s#(${q})deps${q} */ *${q}tech_eval${q} */ *${q}src${q} */ *${q}tech_eval${q}#\\1rtlscout\\1 / \\1tech_eval\\1#g"

  # 2. the module name wherever it is used as a module: imports, `-m tech_eval.x`, dotted strings, prose, and the
  #    name in backticks. Not touched: already-prefixed `rtlscout.tech_eval`, paths (`deps/tech_eval`,
  #    `tech_eval/x`), identifiers containing it (`my_tech_eval`), quoted bare names (`name = "tech_eval"`) and
  #    assignments (`tech_eval = …`).
  files_with 'tech_eval' '*.py' '*.md' '*.sh' '*.yml' '*.yaml' \
    | xargs -0 -r perl -pi -e 's/(?<![\w.\/-])tech_eval(?=[\s.]|$)(?!\s*=)/rtlscout.tech_eval/g;' \
                           -e 's/(?<=`)tech_eval(?=`)/rtlscout.tech_eval/g'
}

case "${1:-}" in
  core|tech_eval) "step_$1" ;;
  *) echo "usage: $0 core | tech_eval" >&2; exit 2 ;;
esac
