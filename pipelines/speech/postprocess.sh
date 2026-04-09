# file: pipelines/speech/postprocess.sh

#!/usr/bin/env bash
set -euo pipefail

INPUT="${1:?full-dialogue.txt required}"

signalnoise postprocess "$INPUT"
