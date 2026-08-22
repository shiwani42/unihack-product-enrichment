#!/usr/bin/env python3
"""Generate a timed natural voiceover and mix it under the ambient score.

Uses OpenAI gpt-4o-mini-tts when available, otherwise tts-1-hd.
Clips are cached by text hash so reruns do not re-bill unchanged lines.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import sys
import urllib.error
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "voiceover_script.json"
CLIPS = ROOT / "audio_build" / "clips"
OUT_VO = ROOT / "public" / "audio" / "voiceover.wav"
OUT_MIX = ROOT / "public" / "audio" / "mix.wav"
SCORE = ROOT / "public" / "audio" / "score.wav"
DURATION_S = 178.0
USE_OPENAI = False  # set True when a valid OPENAI_API_KEY is present


def _pcm_from_wav(path: Path) -> tuple[int, int, bytes]:
    with wave.open(str(path), "rb") as wf:
        return wf.getframerate(), wf.getnchannels(), wf.readframes(wf.getnframes())


def _write_wav(path: Path, rate: int, channels: int, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)


def _to_mono16(src: Path, dest: Path, rate: int) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-i", str(src),
            "-ac", "1", "-ar", str(rate), "-sample_fmt", "s16", str(dest),
        ],
        check=True,
    )


def tts_edge(text: str, dest: Path, voice: str) -> None:
    """Microsoft neural voices via edge-tts. Natural, no API key."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".mp3")
    subprocess.run(
        [
            "edge-tts",
            "--voice", voice,
            "--rate=-6%",
            "--text", text,
            "--write-media", str(tmp),
        ],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(tmp), str(dest)],
        check=True,
    )


def tts_openai(text: str, dest: Path, model: str, voice: str, instructions: str) -> None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("OPENAI_API_KEY is not set")
    payload = {
        "model": model,
        "voice": voice,
        "input": text,
        "response_format": "wav",
    }
    if model.startswith("gpt-4o"):
        payload["instructions"] = instructions
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            dest.write_bytes(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"OpenAI TTS {exc.code}: {body[:400]}") from exc


def synthesize(line: dict, spec: dict) -> Path:
    global USE_OPENAI
    edge_voice = spec.get("edge_voice", "en-US-AndrewNeural")
    digest = hashlib.sha1(
        f"{edge_voice}|{line['text']}".encode()
    ).hexdigest()[:16]
    raw = CLIPS / f"{line['id']}-{digest}.raw.wav"
    cooked = CLIPS / f"{line['id']}-{digest}.wav"
    if cooked.exists() and cooked.stat().st_size > 1000:
        return cooked
    CLIPS.mkdir(parents=True, exist_ok=True)
    if USE_OPENAI:
        try:
            tts_openai(line["text"], raw, spec["model"], spec["voice"], spec["instructions"])
        except (RuntimeError, SystemExit):
            print(f"  OpenAI unavailable; using {edge_voice}")
            USE_OPENAI = False
            tts_edge(line["text"], raw, edge_voice)
    else:
        tts_edge(line["text"], raw, edge_voice)
    _to_mono16(raw, cooked, spec["sample_rate"])
    return cooked


def assemble(spec: dict) -> Path:
    rate = spec["sample_rate"]
    total = int(DURATION_S * rate)
    timeline = bytearray(total * 2)
    for line in spec["lines"]:
        clip = synthesize(line, spec)
        _sr, _ch, pcm = _pcm_from_wav(clip)
        start = int(line["start_s"] * rate)
        end = min(start + len(pcm) // 2, total)
        take = (end - start) * 2
        timeline[start * 2 : start * 2 + take] = pcm[:take]
        dur = (len(pcm) // 2) / rate
        print(f"  {line['id']:16s}  t={line['start_s']:6.1f}s  len={dur:5.2f}s")
        if line["start_s"] + dur > DURATION_S - 0.4:
            print(f"    warn: {line['id']} runs near the end of the film")
    dest = ROOT / "audio_build" / "voiceover_timeline.wav"
    _write_wav(dest, rate, 1, bytes(timeline))
    return dest


def finalize(timeline: Path) -> None:
    OUT_VO.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-i", str(timeline),
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=8",
            "-ar", "48000", "-ac", "2", str(OUT_VO),
        ],
        check=True,
    )
    if not SCORE.exists():
        print(f"score missing ({SCORE}); wrote voiceover only")
        return
    # Quiet ambient bed under speech; leave a little air in the gaps.
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(SCORE),
            "-i", str(OUT_VO),
            "-filter_complex",
            "[0:a]volume=0.18,afade=t=in:st=0:d=1.2,afade=t=out:st=175.5:d=2.4[s];"
            "[1:a]volume=1.05[v];"
            "[s][v]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mix]",
            "-map", "[mix]",
            "-ar", "48000", "-ac", "2",
            str(OUT_MIX),
        ],
        check=True,
    )
    print(f"wrote {OUT_VO}")
    print(f"wrote {OUT_MIX}")


def main() -> None:
    spec = json.loads(SCRIPT.read_text())
    print(f"voice={spec['voice']}  model={spec['model']}")
    timeline = assemble(spec)
    finalize(timeline)


if __name__ == "__main__":
    main()
