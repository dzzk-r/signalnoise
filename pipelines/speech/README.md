# 🎙️ signalnoise — Speech Processing Pipeline 
###### WhisperX + Diarization ed.

## Purpose

This document describes the **speech processing layer** of `signalnoise`.

Its job is to transform raw audio recordings into **structured, speaker-aware transcript artifacts** that can later be converted into:

- requirements
- bugs
- constraints
- architecture signals
- Codex-ready prompts

This is the operational foundation of the larger `signalnoise` system.

---

## Scope

This pipeline is designed for:

- phone recordings (`.amr`, `.m4a`, `.wav`)
- exported messenger calls
- microphone recordings
- system audio captures
- OBS recordings
- future audio extracted from video

It is not limited to one language, one speaker count, or one recording source.

---

## High-Level Flow

```mermaid
flowchart TB
    A[Raw Audio Input] --> B[Normalize with ffmpeg]
    B --> C[Canonical WAV 16kHz mono]
    C --> D[WhisperX VAD]
    D --> E[Transcription]
    E --> F[Alignment]
    F --> G[Pyannote Diarization]
    G --> H[Structured Output]

    H --> I[JSON]
    H --> J[TXT]
    H --> K[SRT / VTT]
    H --> L[TSV]
````

---

## Runtime Layout

This pipeline assumes a broader local AI workspace rather than a self-contained repo-only execution model.

```bash
~/AI/
├── cache/
│   ├── huggingface/      # HF models (whisper, pyannote, related assets)
│   ├── torch/            # torch checkpoints
│   ├── uv/               # uv caches / tool environments
│
├── datasets/
│   ├── raw_audio/        # original recordings
│   ├── processed_audio/  # normalized wav files
│
├── outputs/
│   └── whisperx/
│       ├── 2026-03-22/
│       ├── 2026-03-23/
│
└── systems/
    └── signalnoise/
        ├── repo/         # local clone of the repository
        ├── runs/         # isolated run directories
        ├── configs/      # local configs and templates
        └── logs/         # aggregated or copied logs
```

This separation is intentional:

* `cache/` contains shared model/runtime artifacts
* `datasets/` contains source and normalized audio
* `outputs/` contains generated artifacts
* `systems/signalnoise/` contains system-specific logic and run state

This keeps the pipeline modular, portable, and compatible with platform-style engineering.

---

## Repository-Level Structure

Inside the repository, the speech subsystem is expected to live here:

```bash
signalnoise/
├── README.md
├── pipelines/
│   └── speech/
│       ├── README.md
│       ├── POSTPROCESSING.md
│       ├── run.sh
│       └── postprocess.sh
├── docs/
├── public-process/
│   ├── draft/
│   └── examples/
└── scripts/
```

The repository contains:

* logic
* docs
* wrappers
* examples

The runtime data lives outside the repository under `~/AI/...`.

---

## Supported Inputs

Typical input types:

* `.amr`
* `.wav`
* `.m4a`
* `.mp3`

Potential future inputs:

* OBS recordings
* desktop audio captures
* extracted audio tracks from video files

The pipeline standardizes all inputs before transcription.

---

## Canonical Audio Format

All inputs should be normalized into:

* WAV
* mono
* 16kHz

Example:

```bash
ffmpeg -y -i input.amr -ar 16000 -ac 1 output.wav
```

For video sources:

```bash
ffmpeg -y -i input.mkv -vn -ar 16000 -ac 1 output.wav
```

This keeps downstream processing consistent and predictable.

---

## Model / Runtime Notes

The current working pipeline uses:

* `WhisperX`
* Whisper model: `large-v3`
* `pyannote` diarization
* `cpu`
* `int8` compute type

This configuration was validated on macOS with Apple Silicon CPU execution.

---

## Important Model Format Separation

Whisper tooling is fragmented across incompatible model formats.

| Tool          | Model format                                  |
| ------------- | --------------------------------------------- |
| `whisper.cpp` | `ggml` / `gguf`                               |
| `WhisperX`    | Hugging Face / PyTorch / faster-whisper stack |
| `MacWhisper`  | CoreML / WhisperKit                           |

These formats are **not interchangeable**.

That means:

* a `ggml` model used by `whisper.cpp` is not directly reusable by `WhisperX`
* a CoreML model used by MacWhisper is not directly reusable by `WhisperX`
* `WhisperX` relies on its own stack and cache behavior

This is why centralized cache layout matters.

---

## Cache Strategy

The pipeline should reuse shared caches under `~/AI/cache`.

Recommended environment variables:

```bash
export HF_HOME="$HOME/AI/cache/huggingface"
export TRANSFORMERS_CACHE="$HOME/AI/cache/huggingface"
export HF_DATASETS_CACHE="$HOME/AI/cache/huggingface"

export TORCH_HOME="$HOME/AI/cache/torch"
export UV_CACHE_DIR="$HOME/AI/cache/uv"
```

If data already exists under default cache locations, symbolic links may be used.

Example:

```bash
mkdir -p ~/AI/cache/{huggingface,torch,uv}

mv ~/.cache/huggingface ~/AI/cache/
ln -s ~/AI/cache/huggingface ~/.cache/huggingface

mv ~/.cache/uv ~/AI/cache/
ln -s ~/AI/cache/uv ~/.cache/uv
```

This enables:

* cache reuse
* portability
* less repeated downloading
* predictable storage layout

---

## Token Hygiene (Critical)

Do **not** pass authentication tokens directly in the command line like this:

```bash
--hf_token "hf_xxx"
```

That leaks secrets through:

* process listings (`ps`)
* shell history
* screenshots
* shared logs
* copied terminal output

### Recommended approach

Store tokens in shell secrets:

```bash
# ~/.secrets.zsh
export HF_TOKEN='hf_NEW_TOKEN'
export HUGGINGFACE_HUB_TOKEN="$HF_TOKEN"
```

Load them from `~/.zshrc`:

```bash
[ -f ~/.secrets.zsh ] && source ~/.secrets.zsh
```

Then use:

```bash
--hf_token "$HF_TOKEN"
```

If a token was exposed:

1. revoke it
2. create a new one
3. update the secrets file

---

## Installation

### Preferred approach

Install `whisperx` once rather than relying on `uvx` for every run.

Example:

```bash
uv tool install whisperx
```

Then run:

```bash
whisperx ...
```

### Why not rely on `uvx`?

`uvx whisperx` is convenient, but it is not the best long-term entrypoint because:

* it may attempt package resolution through the network
* it is more fragile offline
* it introduces avoidable uncertainty in repeated runs

This became visible when offline runs failed on package fetch / DNS resolution.

For repeatable pipeline execution, a locally installed tool or dedicated environment is preferred.

---

## Main Command

Typical execution:

```bash
whisperx input.wav \
  --language en \
  --model large-v3 \
  --device cpu \
  --compute_type int8 \
  --diarize \
  --min_speakers 2 \
  --max_speakers 2 \
  --hf_token "$HF_TOKEN" \
  --output_dir output_dir
```

### Notes

* specify `--language` when known
* specify speaker bounds when known
* `int8` is currently the practical CPU setting
* diarization is much less observable than transcription and may look “stalled” while still working

---

## Isolated Run Layout

Each run should have its own working directory.

Example:

```bash
~/AI/systems/signalnoise/runs/2026-03-23_123937_call/
├── input.amr
├── audio.wav
├── run.log
├── meta.json
├── output/
│   ├── file.json
│   ├── file.txt
│   ├── file.srt
│   ├── file.vtt
│   └── file.tsv
└── full-dialogue.txt
```

This makes it easier to:

* compare runs
* archive artifacts
* inspect failures
* correlate input duration with runtime

---

## Recommended Wrapper Flow

The wrapper should perform these steps:

1. copy original input into run directory
2. normalize to canonical WAV
3. launch `whisperx`
4. save full stdout/stderr into `run.log`
5. preserve all output artifacts
6. extract diarized dialogue from `.json`
7. store minimal run metadata

---

## Observability

One of the main weaknesses of the raw `whisperx` experience is poor observability during long runs, especially during diarization.

Recommended wrapper pattern:

```bash
echo "START $(date '+%F %T')" | tee run.log
/usr/bin/time -l whisperx ... 2>&1 | tee -a run.log
echo "END $(date '+%F %T')" | tee -a run.log
```

Useful extraction:

```bash
grep -nE "Performing voice activity detection|Performing transcription|Performing alignment|Performing diarization" run.log
```

This helps identify stage boundaries and estimate where time is spent.

---

## Output Artifacts

Typical outputs:

| File    | Purpose                                                         |
| ------- | --------------------------------------------------------------- |
| `.json` | structured transcript with segments, timing, and speaker labels |
| `.txt`  | flat transcript                                                 |
| `.srt`  | subtitle export                                                 |
| `.vtt`  | web subtitle export                                             |
| `.tsv`  | table-like timing export                                        |

The `.json` file is the main source of truth for downstream processing.

---

## Extracting Full Dialogue

Example:

```bash
jq -r '.segments[] | "\(.speaker // "UNKNOWN") [\(.start)-\(.end)] \(.text)"' file.json
```

This can be redirected into:

```bash
jq -r '.segments[] | "\(.speaker // "UNKNOWN") [\(.start)-\(.end)] \(.text)"' file.json > full-dialogue.txt
```

This is the bridge artifact into the postprocessing layer.

---

## Speaker Normalization

Public or shared artifacts should not expose real participant identities.

Published examples should use normalized role labels such as:

```text
SystemThinker → defines intent, constraints, system logic
CodeRunner    → probes behavior, tests implementation, exposes inconsistencies
```

These are not names. They are reasoning roles.

This makes examples:

* publishable
* reusable
* easier to compare across sessions

---

## Known Non-Blocking Warnings

### `torchcodec` warning

Example pattern:

```text
torchcodec is not installed correctly
```

Observed behavior:

* noisy
* not fatal in current runs
* pipeline still proceeds through transcription, alignment, and diarization

Current classification:

* warning
* not currently a blocker

### `std(): degrees of freedom is <= 0`

Observed during diarization stack execution.

Current classification:

* warning
* not currently a blocker

These warnings should still be documented, but not treated as immediate failures.

---

## Known Critical Failure Modes

### 1. Gated Hugging Face model access

Symptoms:

* `403`
* gated repository error

Cause:

* token exists but access has not been granted / accepted

Resolution:

* accept model terms
* ensure the correct token/account is being used

### 2. Offline `uvx` package resolution failure

Symptoms:

* failure fetching `pypi.org`
* DNS / connection errors

Cause:

* `uvx` tries to resolve packages online

Resolution:

* install `whisperx` locally instead of using `uvx` as primary runner

### 3. Missing output artifacts after completion

Symptoms:

* process exits
* output directory remains empty

Typical next steps:

* inspect `run.log`
* confirm whether crash happened after alignment or diarization
* confirm actual output path

---

## Runtime Characteristics

Based on observed runs:

* normalization is fast
* transcription is visible because transcript lines appear continuously
* alignment is relatively short
* diarization is the least observable stage and may remain quiet for a long time
* output files may only appear at the end of the run

This makes long diarization phases feel “stuck” even when the process is healthy.

---

## Performance Tracking Strategy

To build real runtime intuition, track for each run:

* input file
* input duration
* normalized WAV size
* language
* speaker count bounds
* model
* compute type
* wall time
* success / failure

Useful duration command:

```bash
ffprobe -v error -show_entries format=duration \
-of default=noprint_wrappers=1:nokey=1 \
input.wav
```

This allows future correlation between:

* source duration
* pipeline stage duration
* machine performance
* speaker count
* chosen model size

---

## Minimal Wrapper Example

```bash
#!/usr/bin/env bash
set -euo pipefail

INPUT="$1"
LANG="${2:-en}"
SPEAKERS="${3:-2}"

STAMP="$(date +%F_%H%M%S)"
BASE="$(basename "$INPUT")"
NAME="${BASE%.*}"

RUN_DIR="$HOME/AI/systems/signalnoise/runs/${STAMP}_${NAME}"

mkdir -p "$RUN_DIR/output"
cp "$INPUT" "$RUN_DIR/$BASE"

ffmpeg -y -i "$INPUT" -ar 16000 -ac 1 "$RUN_DIR/${NAME}.wav"

echo "START $(date '+%F %T')" | tee "$RUN_DIR/run.log"

/usr/bin/time -l \
whisperx "$RUN_DIR/${NAME}.wav" \
  --language "$LANG" \
  --model large-v3 \
  --device cpu \
  --compute_type int8 \
  --diarize \
  --min_speakers "$SPEAKERS" \
  --max_speakers "$SPEAKERS" \
  --hf_token "$HF_TOKEN" \
  --output_dir "$RUN_DIR/output" \
2>&1 | tee -a "$RUN_DIR/run.log"

echo "END $(date '+%F %T')" | tee -a "$RUN_DIR/run.log"

JSON_FILE="$(find "$RUN_DIR/output" -name '*.json' | head -1)"

if [ -n "$JSON_FILE" ]; then
  jq -r '.segments[] | "\(.speaker // "UNKNOWN") [\(.start)-\(.end)] \(.text)"' \
    "$JSON_FILE" > "$RUN_DIR/full-dialogue.txt"
fi
```

This is intentionally minimal and should evolve with the system.

---

## Relationship to the Larger System

This speech layer is only the first operational stage of `signalnoise`.

Its responsibility ends at:

* normalized audio
* diarized transcript
* structured transcript artifacts

The next stage begins in:

* `pipelines/speech/POSTPROCESSING.md`

That layer turns transcript artifacts into:

* requirements
* bugs
* constraints
* architecture signals
* Codex-ready execution material

---

## External Runtime Dependencies

This project currently relies on external tools not managed as Python package dependencies:

- ffmpeg
- whisperx
- jq

This is intentional:
- to avoid pulling a heavy ML stack into the base package
- to keep `signalnoise` as an orchestration layer
- to preserve flexibility across environments

---

## Summary

This pipeline is not the whole project.

It is the **signal extraction layer** of `signalnoise`.

Its purpose is to make noisy conversations operationally useful by producing structured, reusable transcript artifacts that can be further transformed into engineering knowledge.

The current implementation is batch-oriented, but the repository structure is intentionally designed to support future real-time STT and streaming ingestion scenarios.
