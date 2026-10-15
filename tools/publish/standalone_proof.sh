#!/usr/bin/env bash
# Standalone proof: install the publish tree into a fresh venv OUTSIDE the working repository and run every suite.
# Resumable: one chunk per call (each call is capped at ~170 s in the sandbox). Usage:
#   bash standalone_proof.sh setup            # copy tree, create venv, pip install -e .
#   bash standalone_proof.sh py_a|py_b|node   # chunks (py_a = tests up to p05, py_b = rest + adapters/agnes-model)
#   bash standalone_proof.sh summary          # print the counts collected so far
# Env: PK_PUBLISH_WORK (default /tmp/publish), AGH_ROOT (default /tmp/aghroot)
set -u
WORK=${PK_PUBLISH_WORK:-/tmp/publish}
P=$WORK/standalone
export UV_LINK_MODE=copy PYTHONDONTWRITEBYTECODE=1
step=${1:-summary}
mkdir -p "$P/results"
case "$step" in
  setup)
    rm -rf "$P/proj" "$P/venv"
    cp -r "$WORK/tree" "$P/proj"
    uv venv --python 3.12 "$P/venv" >/dev/null 2>&1
    uv pip install --python "$P/venv/bin/python" -e "$P/proj" pytest 2>&1 | tail -2
    ;;
  py_a)
    cd "$P/proj" || exit 1
    for d in tests/g2_acceptance tests/p00_contracts tests/p01_store tests/p02_design tests/p03_attempt tests/p04_delivery tests/p05_evidence; do
      timeout 160 "$P/venv/bin/python" -m pytest -p no:cacheprovider -o addopts= -q "$d" > "$P/results/$(basename $d).txt" 2>&1
      echo "$d: $(tail -1 $P/results/$(basename $d).txt)"
    done ;;
  py_b)
    cd "$P/proj" || exit 1
    for d in tests/p06_queries tests/p07_migration tests/p08_knowledge tests/p09_corpus tests/p10_protocol tests/p13_integration tests/p14_science_demo tests/p15_innovation_showcase adapters/agnes-model; do
      timeout 160 "$P/venv/bin/python" -m pytest -p no:cacheprovider -o addopts= -q "$d" > "$P/results/$(basename $d).txt" 2>&1
      echo "$d: $(tail -1 $P/results/$(basename $d).txt)"
    done ;;
  node)
    cd "$P/proj/adapters/agh-plugin" || exit 1
    AGH_ROOT=${AGH_ROOT:-/tmp/aghroot} PK_PYTHON=$P/venv/bin/python PK_HOST_SCRIPT=$PWD/../../tests/p14_science_demo/agh_host.py \
      PK_REGISTRY=$PWD/../../docs/modules/registry.json PK_SKILLS_REGISTRY=$PWD/../../docs/records/skills/registry.json \
      timeout 160 node --test test/*.test.mjs > "$P/results/node_plugin.txt" 2>&1
    echo "plugin: $(grep -E '^# (tests|pass|fail|skipped)' $P/results/node_plugin.txt | tr '\n' ' ')"
    cd "$P/proj" || exit 1
    ln -sfn "$P/venv" .venv   # tests/bridge expects <root>/.venv; a symlink inside the copy, never in the working repo
    PK_PYTHON=$P/venv/bin/python timeout 160 node --test tests/bridge/*_test.mjs > "$P/results/node_bridge.txt" 2>&1
    rm -f .venv
    echo "bridge: $(grep -E '^# (tests|pass|fail|skipped)' $P/results/node_bridge.txt | tr '\n' ' ')" ;;
  summary)
    for f in "$P"/results/*.txt; do printf '%s: ' "$(basename $f .txt)"; (tail -1 "$f" | grep -E 'passed|failed|no tests') || grep -E '^# (tests|pass|fail|skipped)' "$f" | tr '\n' ' '; echo; done ;;
esac
