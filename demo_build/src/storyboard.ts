export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

export const TRANSITION_FRAMES = 18;
export const PROOF_TRANSITION_FRAMES = 12;

export type SceneId =
  | "cold-open"
  | "mechanism"
  | "live-proof"
  | "trust"
  | "close";

export type Scene = {
  id: SceneId;
  durationInFrames: number;
  recording?: string;
};

export const SCENES: Scene[] = [
  {id: "cold-open", durationInFrames: 520},
  {id: "mechanism", durationInFrames: 690},
  {id: "live-proof", durationInFrames: 2700, recording: "recordings/walkthrough.mp4"},
  {id: "trust", durationInFrames: 842},
  {id: "close", durationInFrames: 660},
];

export const TARGET_DURATION_RANGE = [175, 180] as const;

const sceneFrames = SCENES.reduce((total, scene) => {
  if (scene.durationInFrames <= 0) {
    throw new Error(`scene ${scene.id} must have positive duration`);
  }
  return total + scene.durationInFrames;
}, 0);

export const TOTAL_FRAMES =
  sceneFrames - TRANSITION_FRAMES * (SCENES.length - 1);

export const TOTAL_SECONDS = TOTAL_FRAMES / FPS;

export const sceneStart = (id: SceneId): number => {
  let frame = 0;
  for (const scene of SCENES) {
    if (scene.id === id) {
      return frame;
    }
    frame += scene.durationInFrames - TRANSITION_FRAMES;
  }
  throw new Error(`unknown scene ${id}`);
};

export type ProofSegment = {
  id: string;
  durationInFrames: number;
  sourceStartS: number;
  sourceEndS: number;
  caption: string;
  support: string;
};

export const PROOF_TRANSITIONS_COUNT = 5;

export const PROOF_SEGMENTS: ProofSegment[] = [
  {
    id: "proof-intro",
    durationInFrames: 264,
    sourceStartS: 0,
    sourceEndS: 0,
    caption: "Live proof",
    support: "The real app at localhost:8000, recorded in one take.",
  },
  {
    id: "proof-enrich",
    durationInFrames: 540,
    sourceStartS: 11.4,
    sourceEndS: 29.4,
    caption: "Live enrichment",
    support: "One part line in \u2014 a 252-column record out.",
  },
  {
    id: "proof-drawer",
    durationInFrames: 597,
    sourceStartS: 30.2,
    sourceEndS: 50.1,
    caption: "Per-field provenance",
    support: "Every value cites its source URL.",
  },
  {
    id: "proof-batch",
    durationInFrames: 720,
    sourceStartS: 51.0,
    sourceEndS: 75.0,
    caption: "Live enrichment stream",
    support: "1,000 catalog rows classified end-to-end.",
  },
  {
    id: "proof-quality",
    durationInFrames: 330,
    sourceStartS: 89.1,
    sourceEndS: 100.1,
    caption: "Golden benchmarks",
    support: "100% field match against the delivery standard.",
  },
  {
    id: "proof-export",
    durationInFrames: 309,
    sourceStartS: 100.3,
    sourceEndS: 110.6,
    caption: "Delivery-format export",
    support: "CSV, XLSX, and provenance \u2014 ready for PIM upload.",
  },
];

const proofFrames = PROOF_SEGMENTS.reduce(
  (total, segment) => total + segment.durationInFrames,
  0,
);

export const PROOF_TOTAL_FRAMES =
  proofFrames - PROOF_TRANSITION_FRAMES * PROOF_TRANSITIONS_COUNT;

export const SOURCE_RECORDING = {
  file: "recordings/walkthrough.mp4",
  width: 1920,
  height: 1080,
  fps: 30,
  durationS: 110.633,
  frames: 3319,
};

export const REQUIRED_SCREENSHOTS = [
  "screenshots/hero.png",
  "screenshots/enrich_result.png",
  "screenshots/catalog_table.png",
  "screenshots/drawer_sources.png",
  "screenshots/quality_100.png",
  "screenshots/export_page.png",
];

export const REQUIRED_ASSETS = [
  SOURCE_RECORDING.file,
  "audio/score.wav",
  ...REQUIRED_SCREENSHOTS,
];

export const COLORS = {
  paper: "#ffffff",
  ink: "#0d0d0f",
  hairline: "#e8e8ed",
  muted: "#6b6b76",
  green: "#12b76a",
};
