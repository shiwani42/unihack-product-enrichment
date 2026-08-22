import React from "react";
import {AbsoluteFill, useCurrentFrame} from "remotion";
import {COLORS, SANS, MONO, ease, rise, Kicker} from "../components/ui";

const STEPS = [
  {
    n: "01",
    title: "Manufacturer-first sourcing",
    sub: "Resolve the brand before anything else. Official domains only.",
  },
  {
    n: "02",
    title: "Leaf-level classification",
    sub: "14 category templates, 22 indexed leaf nodes.",
  },
  {
    n: "03",
    title: "Evidence extraction",
    sub: "HTML, JSON-LD and PDF spec parsing \u2014 value plus source URL.",
  },
  {
    n: "04",
    title: "Validation",
    sub: "Units, LOV checks, sanity bounds. Blank beats invented.",
  },
  {
    n: "05",
    title: "Delivery format",
    sub: "252 columns composed for PIM upload, provenance attached.",
  },
];

export const Mechanism: React.FC = () => {
  const frame = useCurrentFrame();
  const kicker = ease(frame, 6, 30);
  const headline = ease(frame, 20, 40);
  const caption = ease(frame, 430, 45);

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
          <Kicker>How it answers</Kicker>
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
          A pipeline you can audit.
        </div>

        <div
          style={{
            marginTop: 90,
            display: "flex",
            alignItems: "stretch",
            gap: 0,
          }}
        >
          {STEPS.map((step, index) => {
            const progress = ease(frame, 110 + index * 62, 45);
            return (
              <React.Fragment key={step.n}>
                <div
                  style={{
                    flex: 1,
                    border: `1px solid ${COLORS.hairline}`,
                    borderRadius: 18,
                    padding: "34px 30px",
                    minHeight: 330,
                    display: "flex",
                    flexDirection: "column",
                    gap: 20,
                    background:
                      index === 2 ? "#fbfbfc" : COLORS.paper,
                    ...rise(progress),
                  }}
                >
                  <div
                    style={{
                      fontFamily: MONO,
                      fontSize: 26,
                      color: index === 2 ? COLORS.green : COLORS.muted,
                    }}
                  >
                    {step.n}
                  </div>
                  <div
                    style={{
                      fontFamily: SANS,
                      fontWeight: 700,
                      fontSize: 37,
                      lineHeight: 1.12,
                      color: COLORS.ink,
                    }}
                  >
                    {step.title}
                  </div>
                  <div
                    style={{
                      fontFamily: SANS,
                      fontWeight: 500,
                      fontSize: 26,
                      lineHeight: 1.35,
                      color: COLORS.muted,
                    }}
                  >
                    {step.sub}
                  </div>
                </div>
                {index < STEPS.length - 1 ? (
                  <div
                    style={{
                      width: 56,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontFamily: MONO,
                      fontSize: 30,
                      color: COLORS.muted,
                      opacity: ease(frame, 140 + index * 62, 30),
                    }}
                  >
                    &rarr;
                  </div>
                ) : null}
              </React.Fragment>
            );
          })}
        </div>

        <div
          style={{
            marginTop: "auto",
            display: "flex",
            alignItems: "center",
            gap: 24,
            ...rise(caption),
          }}
        >
          <span
            style={{
              width: 14,
              height: 14,
              borderRadius: 14,
              background: COLORS.green,
            }}
          />
          <span
            style={{
              fontFamily: SANS,
              fontWeight: 600,
              fontSize: 48,
              color: COLORS.ink,
            }}
          >
            Rules first. LLM only for the last mile.{" "}
            <span style={{color: COLORS.muted}}>Blank beats invented.</span>
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
