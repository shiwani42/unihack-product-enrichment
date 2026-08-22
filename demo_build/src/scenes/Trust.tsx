import React from "react";
import {AbsoluteFill, useCurrentFrame} from "remotion";
import {COLORS, SANS, MONO, ease, rise, Kicker, GreenDot} from "../components/ui";

const STATS = [
  {
    numeral: "134/134",
    label: "fields matched vs organizer expected output",
    sub: "2 reference SKUs \u00b7 PDSH4816AF + WDTS7024RZ",
    accent: true,
  },
  {
    numeral: "1000/1000",
    label: "catalog rows classified end-to-end",
    sub: "leaf taxonomy \u00b7 22 indexed nodes",
    accent: true,
  },
  {
    numeral: "77",
    label: "hermetic tests passing",
    sub: "no network required \u00b7 ~2s suite",
    accent: false,
  },
  {
    numeral: "HIGH",
    label: "confidence requires external manufacturer evidence",
    sub: "no evidence \u2192 blank, never invented",
    accent: false,
  },
];

export const Trust: React.FC = () => {
  const frame = useCurrentFrame();
  const kicker = ease(frame, 6, 30);
  const headline = ease(frame, 24, 40);

  return (
    <AbsoluteFill style={{background: COLORS.paper}}>
      <div
        style={{
          position: "absolute",
          left: 140,
          right: 140,
          top: 120,
          bottom: 110,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div style={rise(kicker)}>
          <Kicker>Proven, not promised</Kicker>
        </div>
        <div
          style={{
            marginTop: 34,
            fontFamily: SANS,
            fontWeight: 800,
            fontSize: 96,
            letterSpacing: "-0.02em",
            color: COLORS.ink,
            ...rise(headline),
          }}
        >
          The numbers behind the record.
        </div>

        <div
          style={{
            marginTop: 80,
            flex: 1,
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gridTemplateRows: "1fr 1fr",
            gap: 26,
          }}
        >
          {STATS.map((stat, index) => {
            const progress = ease(frame, 120 + index * 55, 45);
            return (
              <div
                key={stat.numeral}
                style={{
                  border: `1px solid ${COLORS.hairline}`,
                  borderRadius: 22,
                  padding: "44px 52px",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "center",
                  gap: 18,
                  background: stat.accent ? "#fbfbfc" : COLORS.paper,
                  ...rise(progress),
                }}
              >
                <div
                  style={{
                    fontFamily: MONO,
                    fontWeight: 700,
                    fontSize: 118,
                    letterSpacing: "-0.03em",
                    color: stat.accent ? COLORS.ink : COLORS.ink,
                    lineHeight: 1,
                    display: "flex",
                    alignItems: "center",
                    gap: 26,
                  }}
                >
                  {stat.accent ? <GreenDot size={22} /> : null}
                  {stat.numeral}
                </div>
                <div
                  style={{
                    fontFamily: SANS,
                    fontWeight: 600,
                    fontSize: 40,
                    color: COLORS.ink,
                    lineHeight: 1.2,
                  }}
                >
                  {stat.label}
                </div>
                <div
                  style={{
                    fontFamily: MONO,
                    fontSize: 26,
                    color: COLORS.muted,
                  }}
                >
                  {stat.sub}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
