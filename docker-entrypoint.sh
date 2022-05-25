#!/bin/sh
set -ue

# If we were giving command line arguments, run that instead.
if [ ${#} -ne 0 ]; then
  ${@}
  exit
fi

# There are many default environment variables available.
# See: https://docs.github.com/en/actions/learn-github-actions/environment-variables
exec /multiplatform-hashes.py \
  --gh-api-prefix "${GITHUB_API_URL}" \
  --gh-pr-number "$(echo "${GITHUB_REF}" | sed 's@^refs/pull/\([0-9]*\)/merge$@\1@')" \
  --gh-repository "${GITHUB_REPOSITORY}"
