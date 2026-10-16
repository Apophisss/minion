#!/bin/sh
# Prepare a run of OSWorld's office tasks on Minion desktops: OSWorld's tasks and checkers (a clone), the Python
# packages its checkers import, and the folders the harness writes to. Needs git, uv and Minion with Docker.
#
#   OSWORLD_RUN=~/osworld-run sh scripts/osworld/setup.sh
set -eu
RUN="${OSWORLD_RUN:-$HOME/osworld-run}"
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$RUN"
if [ ! -d "$RUN/OSWorld" ]; then
  git clone -q https://github.com/xlang-ai/OSWorld "$RUN/OSWorld"
  git -C "$RUN/OSWorld" checkout -q b138d34  # the tasks and checkers these results were measured with
fi
[ -x "$RUN/venv/bin/python" ] || uv venv -q -p 3.12 "$RUN/venv"
VIRTUAL_ENV="$RUN/venv" uv pip install -q -r "$HERE/requirements.txt"
docker pull -q ghcr.io/apophisss/minion-office:"$(minion --version | sed 's/minion \([0-9]*\.[0-9]*\).*/\1/')" >/dev/null
echo "Ready. Next: $RUN/venv/bin/python $HERE/bench.py plan s1 S <task ids>; bench.py bin s1; bench.py brief s1"
