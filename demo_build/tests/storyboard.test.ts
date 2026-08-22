import {describe, expect, it} from "vitest";
import {execFileSync} from "node:child_process";
import {readFileSync} from "node:fs";
import path from "node:path";
import {
  COLORS,
  FPS,
  PROOF_SEGMENTS,
  PROOF_TOTAL_FRAMES,
  PROOF_TRANSITION_FRAMES,
  REQUIRED_ASSETS,
  SCENES,
  SOURCE_RECORDING,
  TOTAL_FRAMES,
  TRANSITION_FRAMES,
} from "../src/storyboard";

const ROOT = path.resolve(__dirname, "..");
const PUBLIC = path.join(ROOT, "public");

describe("storyboard contract", () => {
  it("has the expected scene order", () => {
    expect(SCENES.map((scene) => scene.id)).toEqual([
      "cold-open",
      "mechanism",
      "live-proof",
      "trust",
      "close",
    ]);
  });

  it("has positive scene durations", () => {
    for (const scene of SCENES) {
      expect(scene.durationInFrames).toBeGreaterThan(0);
    }
  });

  it("computes total frames with transition overlap", () => {
    const sum = SCENES.reduce((acc, scene) => acc + scene.durationInFrames, 0);
    expect(TOTAL_FRAMES).toBe(sum - TRANSITION_FRAMES * (SCENES.length - 1));
  });

  it("lands in the 175-180s challenge window", () => {
    const seconds = TOTAL_FRAMES / FPS;
    expect(seconds).toBeGreaterThanOrEqual(175);
    expect(seconds).toBeLessThanOrEqual(180);
    expect(seconds).toBeCloseTo(178.0, 1);
  });

  it("keeps live proof internally consistent", () => {
    const sum = PROOF_SEGMENTS.reduce(
      (acc, segment) => acc + segment.durationInFrames,
      0,
    );
    expect(PROOF_TOTAL_FRAMES).toBe(
      sum - PROOF_TRANSITION_FRAMES * (PROOF_SEGMENTS.length - 1),
    );
    expect(PROOF_TOTAL_FRAMES).toBe(
      SCENES.find((scene) => scene.id === "live-proof")?.durationInFrames,
    );
    for (const segment of PROOF_SEGMENTS) {
      if (segment.id === "proof-intro") {
        continue; // title card, intentionally no source span
      }
      expect(segment.sourceEndS).toBeGreaterThan(segment.sourceStartS);
    }
  });

  it("declares required real captures that exist", () => {
    for (const asset of REQUIRED_ASSETS) {
      const file = path.join(PUBLIC, asset);
      expect(file, `missing asset ${asset}`).toSatisfy(() => {
        try {
          return readFileSync(file).byteLength > 0;
        } catch {
          return false;
        }
      });
    }
  });

  it("uses the documented palette", () => {
    expect(COLORS.paper).toBe("#ffffff");
    expect(COLORS.ink).toBe("#0d0d0f");
    expect(COLORS.green).toBe("#12b76a");
  });
});

describe("source recording contract", () => {
  const recording = path.join(PUBLIC, SOURCE_RECORDING.file);

  const probe = (): {streams: any[]; format: any} =>
    JSON.parse(
      execFileSync("ffprobe", [
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-count_frames",
        "-show_entries",
        "stream=codec_name,width,height,pix_fmt,r_frame_rate,avg_frame_rate,nb_read_frames:format=duration",
        "-of",
        "json",
        recording,
      ]).toString(),
    );

  it("is an exact-frame 1920x1080 30fps h264 asset", () => {
    const data = probe();
    const stream = data.streams[0];
    expect(stream.codec_name).toBe("h264");
    expect(stream.pix_fmt).toBe("yuv420p");
    expect(stream.width).toBe(1920);
    expect(stream.height).toBe(1080);
    expect(stream.r_frame_rate).toBe("30/1");
    expect(stream.avg_frame_rate).toBe("30/1");
    expect(Number(stream.nb_read_frames)).toBe(SOURCE_RECORDING.frames);
    expect(Number(data.format.duration)).toBeCloseTo(
      SOURCE_RECORDING.durationS,
      2,
    );
  }, 120_000);
});
