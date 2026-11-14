#!/usr/bin/env bash
# Trusted Ubuntu only. Verify the exact official asset; do NOT run its pip setup.
set -euo pipefail
: "${RUNNER_TEMP:?Missing owned runner temporary directory}"
: "${GITHUB_PATH:?Missing Actions PATH file}"
: "${GITHUB_ENV:?Missing Actions environment file}"
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 && "$(uname -m)" == x86_64 ]]
mapfile -t pin < <(python3 - <<'PY'
import json
from pathlib import Path
p = json.loads(Path('perito_dashboard/collector/runtime.json').read_text())['python']
for field in ('url', 'sha256', 'version', 'size', 'executable_sha256'):
    print(p[field])
PY
)
owned=$(mktemp -d "$RUNNER_TEMP/perito-python-XXXXXX")
accepted=false
trap 'if [[ "$accepted" != true ]]; then rm -rf -- "$owned"; fi' EXIT
archive="$owned/python.tar.gz"
curl --proto '=https' --proto-redir '=https' --tlsv1.2 --location --fail --silent --show-error --max-time 180 "${pin[0]}" -o "$archive"
[[ "$(stat -c %s "$archive")" == "${pin[3]}" ]]
printf '%s  %s\n' "${pin[1]}" "$archive" | sha256sum --check --strict
mkdir "$owned/runtime"
tar -xzf "$archive" -C "$owned/runtime"
rm -- "$archive"
# The publisher setup.sh upgrades pip from the network. We deliberately do not
# execute it: the stdlib application needs neither pip nor any installed package.
export PYTHONHOME="$owned/runtime"
export LD_LIBRARY_PATH="$PYTHONHOME/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
printf '%s  %s\n' "${pin[4]}" "$PYTHONHOME/bin/python3" | sha256sum --check --strict
[[ "$("$PYTHONHOME/bin/python3" --version)" == "Python ${pin[2]}" ]]
printf '%s\n' "$PYTHONHOME/bin" >> "$GITHUB_PATH"
printf 'PYTHONHOME=%s\nLD_LIBRARY_PATH=%s\n' "$PYTHONHOME" "$LD_LIBRARY_PATH" >> "$GITHUB_ENV"
"$PYTHONHOME/bin/python3" --version
accepted=true
