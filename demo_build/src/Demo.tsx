import React from "react";
import {
  AbsoluteFill,
  Audio,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import {TransitionSeries, linearTiming} from "@remotion/transitions";
import {fade} from "@remotion/transitions/fade";
import {SCENES, TOTAL_FRAMES, TRANSITION_FRAMES} from "./storyboard";
import {ColdOpen} from "./scenes/ColdOpen";
import {Mechanism} from "./scenes/Mechanism";
import {LiveProof} from "./scenes/LiveProof";
import {Trust} from "./scenes/Trust";
import {Close} from "./scenes/Close";
import {waitForFonts} from "./fonts";

const SceneComponent: React.FC<{id: string}> = ({id}) => {
  if (id === "cold-open") {
    return <ColdOpen />;
  }
  if (id === "mechanism") {
    return <Mechanism />;
  }
  if (id === "live-proof") {
    return <LiveProof />;
  }
  if (id === "trust") {
    return <Trust />;
  }
  return <Close />;
};

const Score: React.FC = () => {
  const frame = useCurrentFrame();
  const volume = interpolate(
    frame,
    [0, 30, TOTAL_FRAMES - 70, TOTAL_FRAMES - 1],
    [0, 0.5, 0.5, 0],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp"},
  );
  return <Audio src={staticFile("audio/score.wav")} volume={volume} />;
};

export const Demo: React.FC = () => {
  waitForFonts();
  return (
    <AbsoluteFill style={{background: "#ffffff"}}>
      <TransitionSeries>
        {SCENES.map((scene, index) => (
          <React.Fragment key={scene.id}>
            {index > 0 ? (
              <TransitionSeries.Transition
                presentation={fade()}
                timing={linearTiming({durationInFrames: TRANSITION_FRAMES})}
              />
            ) : null}
            <TransitionSeries.Sequence durationInFrames={scene.durationInFrames}>
              <SceneComponent id={scene.id} />
            </TransitionSeries.Sequence>
          </React.Fragment>
        ))}
      </TransitionSeries>
      <Score />
    </AbsoluteFill>
  );
};
