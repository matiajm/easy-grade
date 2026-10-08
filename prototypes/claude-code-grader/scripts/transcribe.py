"""Step 1: turn each team's video into a transcript, on this computer.

The video never leaves the machine: faster-whisper runs locally. The first run downloads the
speech model weights once; no student data is sent anywhere.

Usage:  .venv/bin/python scripts/transcribe.py submissions/
Writes: work/<team>/transcript_raw.md and work/<team>/media.json
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

# numpy prints harmless overflow warnings while computing audio features on some Macs.
warnings.filterwarnings("ignore", category=RuntimeWarning)

from common import ROOT, load_config, team_dirs, write_json


def stamp(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcribe each team's presentation locally.")
    parser.add_argument("submissions", help="folder with one subfolder per team")
    parser.add_argument("--work", default=str(ROOT / "work"))
    parser.add_argument("--model", help="whisper model size, e.g. tiny.en, base.en, small.en")
    args = parser.parse_args()

    config = load_config()
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("faster-whisper is not installed. Run: .venv/bin/pip install faster-whisper")

    model_name = args.model or config["whisper_model"]
    print(f"Loading local speech model '{model_name}' (first run downloads it once)...")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    extensions = {e.lower() for e in config["media_extensions"]}
    limit_seconds = config["max_presentation_minutes"] * 60

    for team in team_dirs(args.submissions):
        out = Path(args.work) / team.name
        out.mkdir(parents=True, exist_ok=True)
        media = sorted(f for f in team.iterdir() if f.suffix.lower() in extensions)
        if not media:
            write_json(out / "media.json", {"media_file": None, "problem": "no video or audio file found"})
            print(f"{team.name}: no video found")
            continue

        source = media[0]
        segments, info = model.transcribe(str(source), beam_size=5, vad_filter=False)
        lines, low_confidence = [], []
        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            lines.append(f"[{stamp(seg.start)}] {text}")
            if seg.avg_logprob < config["low_confidence_logprob"] or seg.no_speech_prob > 0.6:
                low_confidence.append(stamp(seg.start))

        duration = round(float(info.duration), 1)
        header = (
            f"# Transcript: {team.name}\n"
            f"Recording length: {stamp(duration)} ({duration} s). "
            "No speaker labels: who is speaking can only be inferred from what is said.\n\n"
        )
        (out / "transcript_raw.md").write_text(header + "\n".join(lines) + "\n")
        write_json(out / "media.json", {
            "media_file": source.name,
            "other_media_files": [m.name for m in media[1:]],
            "duration_seconds": duration,
            "over_time_limit": duration > limit_seconds,
            "time_limit_minutes": config["max_presentation_minutes"],
            "segments": len(lines),
            "low_confidence_at": low_confidence,
            "speaker_labels": False,
        })
        print(f"{team.name}: {len(lines)} segments, {stamp(duration)}"
              + (f", {len(low_confidence)} low-confidence segments" if low_confidence else ""))


if __name__ == "__main__":
    main()
