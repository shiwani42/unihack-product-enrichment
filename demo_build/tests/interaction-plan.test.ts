import {describe, expect, it} from "vitest";
import {readFileSync} from "node:fs";
import path from "node:path";
import {PROOF_SEGMENTS} from "../src/storyboard";

const ROOT = path.resolve(__dirname, "..");
const META_PATH = path.join(ROOT, "recordings", "walkthrough_meta.json");

type Meta = {
  fps: number;
  viewport: {width: number; height: number};
  segments: Record<string, {start: number; end: number}>;
  actions: {
    label: string;
    t: number;
    target?: string;
    x?: number;
    y?: number;
  }[];
  duration_s: number;
};

const meta: Meta = JSON.parse(readFileSync(META_PATH, "utf-8"));

describe("interaction plan contract", () => {
  it("covers every proof segment with real recorded time", () => {
    for (const segment of PROOF_SEGMENTS) {
      if (segment.id === "proof-intro") {
        continue;
      }
      expect(
        segment.sourceStartS,
        `${segment.id} starts before recording`,
      ).toBeGreaterThanOrEqual(0);
      expect(
        segment.sourceEndS,
        `${segment.id} ends past recording end`,
      ).toBeLessThanOrEqual(meta.duration_s + 0.01);
    }
  });

  it("has ordered, uniquely labeled actions inside the viewport", () => {
    const labels = meta.actions.map((action) => action.label);
    expect(new Set(labels).size).toBe(labels.length);
    const times = meta.actions.map((action) => action.t);
    const sorted = [...times].sort((a, b) => a - b);
    expect(times).toEqual(sorted);
    for (const action of meta.actions) {
      if (action.x !== undefined && action.y !== undefined) {
        expect(action.x).toBeGreaterThanOrEqual(0);
        expect(action.x).toBeLessThanOrEqual(meta.viewport.width);
        expect(action.y).toBeGreaterThanOrEqual(0);
        expect(action.y).toBeLessThanOrEqual(meta.viewport.height);
      }
    }
  });

  it("walked the full product path", () => {
    const labels = meta.actions.map((action) => action.label);
    for (const expected of [
      "load-hero",
      "proof-band-visible",
      "click-enrich",
      "nav-catalog",
      "tab-evidence",
      "close-drawer-esc",
      "click-run-batch",
      "batch-complete",
      "click-golden-sku",
      "golden-sku-enriched",
      "click-csv-download",
      "download-saved",
    ]) {
      expect(labels, `missing action ${expected}`).toContain(expected);
    }
  });

  it("declared segments are contiguous across the recording", () => {
    const spans = Object.values(meta.segments);
    for (let index = 1; index < spans.length; index += 1) {
      expect(spans[index].start).toBeCloseTo(spans[index - 1].end, 3);
    }
    const last = spans[spans.length - 1];
    expect(last.end).toBeCloseTo(meta.duration_s, 2);
  });
});
