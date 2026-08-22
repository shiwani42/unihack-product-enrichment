import React from "react";
import {Composition} from "remotion";
import {Demo} from "./Demo";
import {FPS, HEIGHT, TOTAL_FRAMES, WIDTH} from "./storyboard";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Demo"
      component={Demo}
      durationInFrames={TOTAL_FRAMES}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
    />
  );
};
