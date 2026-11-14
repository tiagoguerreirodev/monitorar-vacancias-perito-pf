#!/usr/bin/env bash
# Invoked only by the trusted refresh job, after validation and a complete build.
set -euo pipefail

: "${GH_TOKEN:?Missing repository token}"
: "${GITHUB_OUTPUT:?Missing Actions output file}"
auth=$(printf 'x-access-token:%s' "$GH_TOKEN" | base64 | tr -d '\n')
printf '::add-mask::%s\n' "$auth"
# Scope credentials to this process and GitHub HTTPS; never persist them in Git.
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0=http.https://github.com/.extraheader
export GIT_CONFIG_VALUE_0="AUTHORIZATION: basic $auth"

: "${EXPECTED_REVISION:?Missing validated checkout revision}"
if [[ "$(git rev-parse HEAD)" != "$EXPECTED_REVISION" ]]; then
  echo '::error::Validated checkout changed; refusing to persist a different code/data revision.' >&2
  exit 1
fi
if ! git diff --cached --quiet; then
  echo '::error::Git index is not empty; refusing to commit unvalidated staged changes.' >&2
  exit 1
fi
git fetch --no-tags origin refs/heads/main
if [[ "$(git rev-parse FETCH_HEAD)" != "$EXPECTED_REVISION" ]]; then
  echo '::error::main changed during refresh; discard this candidate and run a fresh workflow on main.' >&2
  exit 1
fi

git add -- data/history.json data/status.json
if ! git diff --cached --quiet; then
  git -c user.name='github-actions[bot]' \
      -c user.email='41898282+github-actions[bot]@users.noreply.github.com' \
      commit -m 'Update verified PF/PCF aggregates (#1)'
  if ! git push origin HEAD:refs/heads/main; then
    echo '::error::Push rejected or failed; never force push. Inspect main and token/branch permissions, then run a fresh workflow on main.' >&2
    exit 1
  fi
fi
printf 'revision=%s\n' "$(git rev-parse HEAD)" >> "$GITHUB_OUTPUT"
