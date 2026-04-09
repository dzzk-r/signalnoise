# file: pipelines/speech/run.sh

#!/usr/bin/env bash
set -euo pipefail

INPUT="${1:?input file required}"
LANG="${2:-en}"
SPEAKERS="${3:-2}"

signalnoise run "$INPUT" --lang "$LANG" --speakers "$SPEAKERS"
