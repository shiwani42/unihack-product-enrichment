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
    durationInFrames: 500,
    sourceStartS: 9.566,
    sourceEndS: 26.229,
    caption: "Live enrichment",
    support: "One part line in \u2014 a 252-column record out.",
  },
  {
    id: "proof-drawer",
    durationInFrames: 583,
    sourceStartS: 26.229,
    sourceEndS: 45.67,
    caption: "Per-field provenance",
    support: "Every value cites its source; blanks stay honest.",
  },
  {
    id: "proof-batch",
    durationInFrames: 1124,
    sourceStartS: 45.67,
    sourceEndS: 83.12,
    caption: "Live enrichment stream",
    support: "1,000 catalog rows classified end-to-end.",
  },
  {
    id: "proof-quality",
    durationInFrames: 376,
    sourceStartS: 83.12,
    sourceEndS: 95.647,
    caption: "Golden accuracy",
    support: "100% field match against the delivery standard, one click from home.",
  },
  {
    id: "proof-export",
    durationInFrames: 298,
    sourceStartS: 95.647,
    sourceEndS: 105.567,
    caption: "Delivery-format export",
    support: "CSV, XLSX and provenance \u2014 one click from the catalog.",
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
  durationS: 105.567,
  frames: 3167,
};

export const REQUIRED_SCREENSHOTS = [
  "screenshots/hero.png",
  "screenshots/enrich_result.png",
  "screenshots/catalog_table.png",
  "screenshots/drawer_evidence.png",
  "screenshots/proof_band.png",
  "screenshots/catalog_export.png",
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
