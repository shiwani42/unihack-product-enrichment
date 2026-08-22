import React from "react";
import {AbsoluteFill, useCurrentFrame} from "remotion";
import {COLORS, SANS, MONO, ease, rise, GreenDot} from "../components/ui";

export const Close: React.FC = () => {
  const frame = useCurrentFrame();
  const mark = rise(ease(frame, 10, 40));
  const tagline = rise(ease(frame, 60, 40));
  const url = rise(ease(frame, 110, 40));
  const team = rise(ease(frame, 160, 40));

  return (
    <AbsoluteFill style={{background: COLORS.paper}}>
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(900px 500px at 50% 30%, rgba(18,183,106,0.05), transparent 65%)",
        }}
      />
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 34,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 30,
            ...mark,
          }}
        >
          <span
            style={{
              width: 34,
              height: 34,
              borderRadius: 34,
              background: COLORS.ink,
            }}
          />
          <span
            style={{
              fontFamily: SANS,
              fontWeight: 800,
              fontSize: 168,
              letterSpacing: "-0.03em",
              color: COLORS.ink,
              lineHeight: 1,
            }}
          >
            unilog
          </span>
          <GreenDot size={34} />
        </div>

        <div
          style={{
            fontFamily: SANS,
            fontWeight: 600,
            fontSize: 54,
            color: COLORS.ink,
            textAlign: "center",
            maxWidth: 1300,
            lineHeight: 1.25,
            ...tagline,
          }}
        >
          Evidence-first product intelligence
          <br />
          for industrial commerce.
        </div>

        <div
          style={{
            fontFamily: MONO,
            fontSize: 32,
            color: COLORS.muted,
            border: `1px solid ${COLORS.hairline}`,
            borderRadius: 999,
            padding: "18px 38px",
            ...url,
          }}
        >
          github.com/shiwani42/unihack-product-enrichment
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 16,
            fontFamily: MONO,
            fontSize: 26,
            letterSpacing: "0.2em",
            textTransform: "uppercase",
            color: COLORS.muted,
            ...team,
          }}
        >
          built by thExplorers &middot; unihack 2026
        </div>
      </div>
    </AbsoluteFill>
  );
};
