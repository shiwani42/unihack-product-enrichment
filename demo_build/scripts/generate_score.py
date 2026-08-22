#!/usr/bin/env python3
"""Generate a deterministic ambient demo score with no external dependencies."""

import argparse
import math
import struct
import wave
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--duration", type=float, default=45.0)
    parser.add_argument("--sample-rate", type=int, default=44_100)
    parser.add_argument("--bpm", type=float, default=100.0)
    return parser.parse_args()


def render(output: Path, duration: float, sample_rate: int, bpm: float) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    beat = 60 / bpm
    impacts = tuple(duration * ratio for ratio in (0.12, 0.27, 0.43, 0.57, 0.72, 0.86))

    def envelope(time_seconds: float) -> float:
        fade_in = min(1.0, time_seconds / 1.5)
        fade_out = min(1.0, (duration - time_seconds) / 2.0)
        return max(0.0, min(fade_in, fade_out))

    def value(sample_index: int) -> tuple[int, int]:
        time_seconds = sample_index / sample_rate
        pad = (
            math.sin(2 * math.pi * 55.0 * time_seconds) * 0.11
            + math.sin(2 * math.pi * 82.41 * time_seconds) * 0.065
            + math.sin(2 * math.pi * 110.0 * time_seconds) * 0.035
        )
        beat_phase = time_seconds % beat
        kick = 0.0
        if beat_phase <= 0.20:
            frequency = 78 - 38 * (beat_phase / 0.20)
            kick = (
                math.sin(2 * math.pi * frequency * beat_phase)
                * math.exp(-beat_phase * 19)
                * 0.24
            )
        impact = 0.0
        for start in impacts:
            phase = time_seconds - start
            if 0 <= phase <= 0.65:
                impact += math.sin(2 * math.pi * 49 * phase) * math.exp(-phase * 7) * 0.23
        shimmer_phase = time_seconds % (beat / 2)
        shimmer = 0.0
        if shimmer_phase <= 0.055:
            noise = math.sin(sample_index * 12.9898) * 43_758.5453
            noise = (noise - math.floor(noise)) * 2 - 1
            shimmer = noise * math.exp(-shimmer_phase * 58) * 0.055
        mixed = (pad + kick + impact + shimmer) * envelope(time_seconds)
        left = max(-1.0, min(1.0, mixed + shimmer * 0.20))
        right = max(-1.0, min(1.0, mixed - shimmer * 0.20))
        return int(left * 32_767), int(right * 32_767)

    with wave.open(str(output), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        chunk = bytearray()
        for sample_index in range(int(sample_rate * duration)):
            chunk.extend(struct.pack("<hh", *value(sample_index)))
            if len(chunk) >= 256 * 1024:
                audio.writeframesraw(chunk)
                chunk.clear()
        if chunk:
            audio.writeframesraw(chunk)


def main() -> None:
    args = parse_args()
    if args.duration <= 0 or args.sample_rate <= 0 or args.bpm <= 0:
        raise SystemExit("duration, sample rate, and BPM must be positive")
    render(args.output, args.duration, args.sample_rate, args.bpm)
    print(f"generated {args.output} ({args.duration:.2f}s)")


if __name__ == "__main__":
    main()
