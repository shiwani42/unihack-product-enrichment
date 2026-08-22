import React from "react";
import {AbsoluteFill, useCurrentFrame} from "remotion";
import {COLORS, SANS, MONO, ease, rise, Kicker, GreenDot} from "../components/ui";

const COLUMN_LABELS = ["MPN", "BRAND", "DESCRIPTION", "CATEGORY", "SPECS", "PRICE"];
const COLUMN_VALUES = [
  "DCB518ASTS06G",
  "Diablo\u00ae",
  "1/2 x 18 in. sanding belt",
  "\u2014",
  "\u2014",
  "\u2014",
];

export const ColdOpen: React.FC = () => {
  const frame = useCurrentFrame();
  const kicker = ease(frame, 8, 30);
  const headline = ease(frame, 24, 40);
  const row = ease(frame, 150, 45);
  const headlineDim = 1 - 0.45 * ease(frame, 150, 40);
  const footer = ease(frame, 330, 40);

  return (
    <AbsoluteFill style={{background: COLORS.ink}}>
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(1200px 700px at 30% 20%, rgba(255,255,255,0.07), transparent 60%)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 140,
          top: 130,
          right: 140,
          bottom: 120,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div style={{...rise(kicker), display: "flex", alignItems: "center", gap: 18}}>
          <span style={{display: "flex", alignItems: "center", gap: 14}}>
            <GreenDot size={16} />
            <span
              style={{
                fontFamily: SANS,
                fontWeight: 700,
                fontSize: 30,
                color: COLORS.paper,
              }}
            >
              unilog
            </span>
          </span>
          <Kicker dark>UniHack &middot; Product Intelligence for Industrial Commerce</Kicker>
        </div>

        <div
          style={{
            marginTop: 90,
            fontFamily: SANS,
            fontWeight: 800,
            fontSize: 118,
            lineHeight: 1.04,
            letterSpacing: "-0.02em",
            color: COLORS.paper,
            opacity: headlineDim,
            transform: `${(1 - headline) * 36 > 0 ? `translateY(${(1 - headline) * 36}px)` : "none"}`,
          }}
        >
          Distributors hand you
          <br />
          six columns.
        </div>

        <div
          style={{
            marginTop: 84,
            display: "flex",
            gap: 14,
            ...rise(row),
          }}
        >
          {COLUMN_LABELS.map((label, index) => {
            const filled = COLUMN_VALUES[index] !== "\u2014";
            return (
              <div
                key={label}
                style={{
                  flex: 1,
                  border: `1px solid ${filled ? "rgba(255,255,255,0.28)" : "rgba(255,255,255,0.12)"}`,
                  borderRadius: 14,
                  padding: "22px 24px",
                  display: "flex",
                  flexDirection: "column",
                  gap: 12,
                }}
              >
                <div
                  style={{
                    fontFamily: MONO,
                    fontSize: 20,
                    letterSpacing: "0.18em",
                    color: filled ? COLORS.green : "rgba(255,255,255,0.35)",
                  }}
                >
                  {label}
                </div>
                <div
                  style={{
                    fontFamily: MONO,
                    fontWeight: filled ? 600 : 400,
                    fontSize: label === "MPN" ? 27 : 23,
                    color: filled ? COLORS.paper : "rgba(255,255,255,0.3)",
                    whiteSpace: "nowrap",
                  }}
                >
                  {COLUMN_VALUES[index]}
                </div>
              </div>
            );
          })}
        </div>

        <div
          style={{
            marginTop: "auto",
            display: "flex",
            alignItems: "baseline",
            gap: 28,
            ...rise(footer),
          }}
        >
          <span
            style={{
              fontFamily: SANS,
              fontWeight: 800,
              fontSize: 64,
              color: COLORS.paper,
            }}
          >
            Six columns in. <span style={{color: COLORS.green}}>252 out.</span>
          </span>
          <span
            style={{
              fontFamily: MONO,
              fontSize: 26,
              color: "rgba(255,255,255,0.5)",
            }}
          >
            proven, not promised
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
