import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  OffthreadVideo,
  staticFile,
} from "remotion";
import {TransitionSeries, linearTiming} from "@remotion/transitions";
import {fade} from "@remotion/transitions/fade";
import {
  COLORS,
  SANS,
  MONO,
  ease,
  rise,
  BrowserFrame,
  Caption,
  GreenDot,
} from "../components/ui";
import {PROOF_SEGMENTS, PROOF_TRANSITION_FRAMES} from "../storyboard";

const Zoom: React.FC<{
  children: React.ReactNode;
  from?: number;
  to?: number;
}> = ({children, from = 1.0, to = 1.055}) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const scale = interpolate(frame, [0, durationInFrames], [from, to], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{overflow: "hidden"}}>
      <AbsoluteFill style={{transform: `scale(${scale})`}}>{children}</AbsoluteFill>
    </AbsoluteFill>
  );
};

const VideoSegment: React.FC<{sourceStartS: number; sourceEndS: number}> = ({
  sourceStartS,
  sourceEndS,
}) => {
  const {fps} = useVideoConfig();
  return (
    <OffthreadVideo
      muted
      src={staticFile("recordings/walkthrough.mp4")}
      startFrom={Math.round(sourceStartS * fps)}
      endAt={Math.round(sourceEndS * fps)}
      style={{
        width: "100%",
        height: "100%",
        objectFit: "cover",
        objectPosition: "center",
      }}
    />
  );
};

const ProofIntro: React.FC = () => {
  const frame = useCurrentFrame();
  const badge = rise(ease(frame, 10, 35));
  const title = rise(ease(frame, 40, 45));
  const sub = rise(ease(frame, 80, 45));
  const strip = rise(ease(frame, 130, 45));
  return (
    <AbsoluteFill
      style={{
        background: COLORS.ink,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 30,
      }}
    >
      <div style={{...badge, display: "flex", alignItems: "center", gap: 16}}>
        <GreenDot size={16} />
        <span
          style={{
            fontFamily: MONO,
            fontSize: 28,
            letterSpacing: "0.24em",
            textTransform: "uppercase",
            color: "rgba(255,255,255,0.6)",
          }}
        >
          live proof &middot; localhost:8000
        </span>
      </div>
      <div
        style={{
          fontFamily: SANS,
          fontWeight: 800,
          fontSize: 128,
          color: COLORS.paper,
          letterSpacing: "-0.02em",
          ...title,
        }}
      >
        Watch it work.
      </div>
      <div
        style={{
          fontFamily: SANS,
          fontWeight: 500,
          fontSize: 40,
          color: "rgba(255,255,255,0.66)",
          ...sub,
        }}
      >
        One continuous take. No cuts inside a step, no mocked data.
      </div>
      <div
        style={{
          marginTop: 30,
          display: "flex",
          gap: 16,
          fontFamily: MONO,
          fontSize: 24,
          color: "rgba(255,255,255,0.55)",
          ...strip,
        }}
      >
        {["enrich", "provenance", "batch", "quality", "export"].map((step, i) => (
          <span
            key={step}
            style={{
              border: "1px solid rgba(255,255,255,0.2)",
              borderRadius: 999,
              padding: "12px 26px",
            }}
          >
            {String(i + 1).padStart(2, "0")} {step}
          </span>
        ))}
      </div>
    </AbsoluteFill>
  );
};

const ProofStep: React.FC<{
  segmentIndex: number;
  zoomFrom?: number;
  zoomTo?: number;
}> = ({segmentIndex, zoomFrom = 1.0, zoomTo = 1.05}) => {
  const frame = useCurrentFrame();
  const segment = PROOF_SEGMENTS[segmentIndex];
  const captionIn = rise(ease(frame, 26, 40));
  const captionShift = (1 - ease(frame, 26, 40)) * 24;
  return (
    <AbsoluteFill style={{background: "#f6f6f8"}}>
      <div
        style={{
          position: "absolute",
          inset: "70px 90px 150px 90px",
        }}
      >
        <BrowserFrame>
          <Zoom from={zoomFrom} to={zoomTo}>
            <VideoSegment
              sourceStartS={segment.sourceStartS}
              sourceEndS={segment.sourceEndS}
            />
          </Zoom>
        </BrowserFrame>
      </div>
      <div
        style={{
          position: "absolute",
          left: 90,
          bottom: 46,
          width: 900,
          transform: `translateY(${captionShift}px)`,
          opacity: captionIn.opacity,
        }}
      >
        <Caption
          kicker={segment.caption}
          title={segment.support}
          dark
        />
      </div>
      <div
        style={{
          position: "absolute",
          right: 90,
          bottom: 52,
          fontFamily: MONO,
          fontSize: 24,
          color: "rgba(255,255,255,0.85)",
          background: "rgba(13,13,15,0.7)",
          borderRadius: 999,
          padding: "12px 24px",
          opacity: captionIn.opacity,
        }}
      >
        take 01 &middot; {segment.sourceStartS.toFixed(1)}s&ndash;
        {segment.sourceEndS.toFixed(1)}s
      </div>
    </AbsoluteFill>
  );
};

export const LiveProof: React.FC = () => {
  return (
    <TransitionSeries>
      {PROOF_SEGMENTS.map((segment, index) => (
        <React.Fragment key={segment.id}>
          {index > 0 ? (
            <TransitionSeries.Transition
              presentation={fade()}
              timing={linearTiming({durationInFrames: PROOF_TRANSITION_FRAMES})}
            />
          ) : null}
          <TransitionSeries.Sequence durationInFrames={segment.durationInFrames}>
            {index === 0 ? (
              <ProofIntro />
            ) : (
              <ProofStep
                segmentIndex={index}
                zoomFrom={1.0}
                zoomTo={index % 2 === 1 ? 1.05 : 1.035}
              />
            )}
          </TransitionSeries.Sequence>
        </React.Fragment>
      ))}
    </TransitionSeries>
  );
};
