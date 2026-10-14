#!/usr/bin/env bash
# Re-verify the framework integrations: one throwaway venv per framework (installed with the same
# packages as docs/integrations.md), then each <framework>_mcp.py connects to Minion's MCP server,
# lists its tools and calls desktop(action="profiles"). No API keys needed; no desktop is created.
#
#   examples/frameworks/check_all.sh                         # all frameworks, server: uvx minion-desktop mcp
#   MINION_MCP="minion mcp" examples/frameworks/check_all.sh langchain crewai
#
# Needs uv (https://docs.astral.sh/uv/). Venvs go to ${TMPDIR:-/tmp}/minion-frameworks.
set -u
cd "$(dirname "$0")" || exit 1

packages() {
  case $1 in
    openai_agents) echo "openai-agents" ;;
    langchain) echo "langchain-mcp-adapters langchain[openai]" ;;
    llamaindex) echo "llama-index-tools-mcp llama-index-llms-openai" ;;
    crewai) echo "crewai crewai-tools[mcp]" ;;
    smolagents) echo "smolagents[mcp] mcp<2" ;;                         # mcpadapt 0.1.20 breaks on mcp 2.x
    pydantic_ai) echo "pydantic-ai-slim[mcp,openai]" ;;
    google_adk) echo "google-adk[mcp]" ;;
    autogen) echo "autogen-agentchat autogen-ext[mcp,openai] mcp<2" ;;  # autogen-ext 0.7.5 breaks on mcp 2.x
    *) return 1 ;;
  esac
}

all="openai_agents langchain llamaindex crewai smolagents pydantic_ai google_adk autogen"
limit=$(command -v timeout >/dev/null && echo "timeout 300")
root=${TMPDIR:-/tmp}/minion-frameworks
status=0
for fw in ${*:-$all}; do
  pkgs=$(packages "$fw") || { echo "FAIL $fw (unknown; choose from: $all)"; status=1; continue; }
  venv=$root/$fw
  [ -d "$venv" ] || uv venv -q --python 3.12 "$venv" || { echo "FAIL $fw (venv)"; status=1; continue; }
  # shellcheck disable=SC2086
  if ! uv pip install -q --python "$venv/bin/python" $pkgs; then
    echo "FAIL $fw (install)"; status=1; continue
  fi
  if out=$(CREWAI_TELEMETRY_OPT_OUT=true $limit "$venv/bin/python" "${fw}_mcp.py" 2>&1); then
    echo "ok   $fw: $(echo "$out" | grep -m1 '^Loaded')"
  else
    echo "FAIL $fw"; echo "$out" | tail -n 8; status=1
  fi
done
exit $status
