# pipelines/speech/cli.py

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_cmd(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    stdout=None,
    stderr=None,
) -> int:
    print(f"[exec] {' '.join(shlex.quote(x) for x in cmd)}")
    completed = subprocess.run(cmd, env=env, stdout=stdout, stderr=stderr, text=True)
    return completed.returncode


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def default_env() -> dict[str, str]:
    home = Path.home()
    env = os.environ.copy()

    hf_home = env.get("HF_HOME", str(home / "AI/cache/huggingface"))
    env.setdefault("HF_HOME", hf_home)
    env.setdefault("TRANSFORMERS_CACHE", hf_home)
    env.setdefault("HF_DATASETS_CACHE", hf_home)
    env.setdefault("TORCH_HOME", str(home / "AI/cache/torch"))
    env.setdefault("UV_CACHE_DIR", str(home / "AI/cache/uv"))

    return env


def extract_dialogue_from_json(json_file: Path, output_file: Path) -> None:
    jq = shutil.which("jq")
    if jq:
        cmd = [
            jq,
            "-r",
            '.segments[] | "\\(.speaker // \\"UNKNOWN\\") [\\(.start)-\\(.end)] \\(.text)"',
            str(json_file),
        ]
        with output_file.open("w", encoding="utf-8") as out:
            completed = subprocess.run(cmd, stdout=out, stderr=subprocess.PIPE, text=True)
        if completed.returncode == 0:
            return
        print(f"[warn] jq extraction failed: {completed.stderr.strip()}", file=sys.stderr)

    # Fallback without jq
    data = json.loads(json_file.read_text(encoding="utf-8"))
    segments = data.get("segments") or data.get("word_segments") or []

    with output_file.open("w", encoding="utf-8") as out:
        for seg in segments:
            speaker = seg.get("speaker", "UNKNOWN")
            start = seg.get("start", "")
            end = seg.get("end", "")
            text = seg.get("text", "")
            out.write(f"{speaker} [{start}-{end}] {text}\n")


def cmd_run(args: argparse.Namespace) -> int:
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    env = default_env()
    hf_token = require_env("HF_TOKEN")

    home = Path.home()
    base_dir = Path(
        os.environ.get(
            "SIGNALNOISE_HOME",
            str(home / "AI" / "systems" / "signalnoise"),
        )
    ).expanduser().resolve()

    name = input_path.stem
    run_dir = base_dir / "runs" / f"{now_stamp()}_{name}"
    output_dir = run_dir / "output"
    ensure_dir(output_dir)

    copied_input = run_dir / input_path.name
    wav_path = run_dir / f"{name}.wav"
    log_path = run_dir / "run.log"
    dialogue_path = run_dir / "full-dialogue.txt"
    meta_path = run_dir / "meta.json"

    shutil.copy2(input_path, copied_input)

    meta = {
        "input": str(input_path),
        "copied_input": str(copied_input),
        "run_dir": str(run_dir),
        "language": args.lang,
        "speakers": args.speakers,
        "model": args.model,
        "device": args.device,
        "compute_type": args.compute_type,
        "created_at": datetime.now().isoformat(),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ar",
        "16000",
        "-ac",
        "1",
        str(wav_path),
    ]
    rc = run_cmd(ffmpeg_cmd, env=env)
    if rc != 0:
        print("[error] ffmpeg failed", file=sys.stderr)
        return rc

    whisperx_cmd = [
        "whisperx",
        str(wav_path),
        "--language",
        args.lang,
        "--model",
        args.model,
        "--device",
        args.device,
        "--compute_type",
        args.compute_type,
        "--diarize",
        "--min_speakers",
        str(args.speakers),
        "--max_speakers",
        str(args.speakers),
        "--hf_token",
        hf_token,
        "--output_dir",
        str(output_dir),
    ]

    time_cmd = ["/usr/bin/time", "-l", *whisperx_cmd]

    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write(f"START {datetime.now().isoformat()}\n")
        log_file.flush()
        completed = subprocess.run(
            time_cmd,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        log_file.write(f"END {datetime.now().isoformat()}\n")

    if completed.returncode != 0:
        print(f"[error] whisperx failed. See log: {log_path}", file=sys.stderr)
        return completed.returncode

    json_files = list(output_dir.glob("*.json"))
    if not json_files:
        print(f"[warn] No JSON output found in {output_dir}", file=sys.stderr)
        return 0

    json_file = max(json_files, key=lambda p: p.stat().st_mtime)
    extract_dialogue_from_json(json_file, dialogue_path)

    print(f"[done] run_dir={run_dir}")
    print(f"[done] dialogue={dialogue_path}")
    return 0


def cmd_postprocess(args: argparse.Namespace) -> int:
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    out_dir = input_path.parent / "postprocessed"
    ensure_dir(out_dir)

    target = out_dir / "dialogue.txt"
    shutil.copy2(input_path, target)

    print(f"[done] prepared postprocessing input: {target}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="signalnoise",
        description="Speech pipeline entrypoint for signalnoise",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run speech pipeline on an input audio file")
    run_p.add_argument("input", help="Path to input audio file")
    run_p.add_argument("--lang", default="en", help="Language hint, default: en")
    run_p.add_argument("--speakers", type=int, default=2, help="Exact speaker count")
    run_p.add_argument("--model", default="large-v3", help="Whisper model")
    run_p.add_argument("--device", default="cpu", help="Execution device")
    run_p.add_argument("--compute-type", default="int8", help="Compute type")
    run_p.set_defaults(func=cmd_run)

    post_p = sub.add_parser("postprocess", help="Prepare full-dialogue.txt for the next layer")
    post_p.add_argument("input", help="Path to full-dialogue.txt")
    post_p.set_defaults(func=cmd_postprocess)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    rc = args.func(args)
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
