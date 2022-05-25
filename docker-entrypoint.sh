#!/bin/sh
set -ue

# If we were giving command line arguments, run that instead.
if [ ${#} -ne 0 ]; then
  ${@}
  exit
fi

exec /multiplatform-hashes.py
