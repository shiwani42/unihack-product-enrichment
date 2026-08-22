import {staticFile} from "remotion";
import {loadFont} from "@remotion/fonts";
import {continueRender, delayRender} from "remotion";

const FAMILIES: {family: string; file: string; weight: number}[] = [
  {family: "Inter", file: "Inter-400.woff2", weight: 400},
  {family: "Inter", file: "Inter-500.woff2", weight: 500},
  {family: "Inter", file: "Inter-600.woff2", weight: 600},
  {family: "Inter", file: "Inter-700.woff2", weight: 700},
  {family: "Inter", file: "Inter-800.woff2", weight: 800},
  {family: "JetBrains Mono", file: "JetBrainsMono-400.woff2", weight: 400},
  {family: "JetBrains Mono", file: "JetBrainsMono-600.woff2", weight: 600},
  {family: "JetBrains Mono", file: "JetBrainsMono-700.woff2", weight: 700},
];

let handle: number | null = null;

export const waitForFonts = (): void => {
  if (handle !== null) {
    return;
  }
  handle = delayRender("loading fonts");
  const done = handle;
  Promise.all(
    FAMILIES.map((entry) =>
      loadFont({
        family: entry.family,
        url: staticFile(`fonts/${entry.file}`),
        weight: String(entry.weight),
      }),
    ),
  )
    .then(() => continueRender(done))
    .catch((error) => {
      continueRender(done);
      throw error;
    });
};

export const SANS = "Inter, -apple-system, BlinkMacSystemFont, sans-serif";
export const MONO = "'JetBrains Mono', 'SFMono-Regular', Menlo, monospace";
