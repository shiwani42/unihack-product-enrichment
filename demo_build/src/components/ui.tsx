import React from "react";
import {interpolate, Easing, staticFile} from "remotion";

export const COLORS = {
  paper: "#ffffff",
  ink: "#0d0d0f",
  hairline: "#e8e8ed",
  muted: "#6b6b76",
  green: "#12b76a",
};

export const SANS = "Inter, -apple-system, BlinkMacSystemFont, sans-serif";
export const MONO = "'JetBrains Mono', 'SFMono-Regular', Menlo, monospace";

export const ease = (frame: number, start: number, duration: number): number =>
  interpolate(frame, [start, start + duration], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

export const rise = (
  progress: number,
  distance = 36,
): React.CSSProperties => ({
  opacity: progress,
  transform: `translateY(${(1 - progress) * distance}px)`,
});

export const Kicker: React.FC<{children: React.ReactNode; dark?: boolean}> = ({
  children,
  dark,
}) => (
  <div
    style={{
      fontFamily: MONO,
      fontSize: 26,
      letterSpacing: "0.22em",
      textTransform: "uppercase",
      color: dark ? "rgba(255,255,255,0.55)" : COLORS.muted,
    }}
  >
    {children}
  </div>
);

export const Caption: React.FC<{
  kicker: string;
  title: string;
  support?: string;
  dark?: boolean;
}> = ({kicker, title, support, dark}) => (
  <div
    style={{
      display: "flex",
      flexDirection: "column",
      gap: 14,
      padding: "34px 44px",
      background: dark ? "rgba(13,13,15,0.86)" : "rgba(255,255,255,0.94)",
      border: `1px solid ${dark ? "rgba(255,255,255,0.14)" : COLORS.hairline}`,
      borderRadius: 18,
      boxShadow: dark ? "none" : "0 18px 50px rgba(13,13,15,0.08)",
    }}
  >
    <div
      style={{
        fontFamily: MONO,
        fontSize: 24,
        letterSpacing: "0.2em",
        textTransform: "uppercase",
        color: COLORS.green,
      }}
    >
      {kicker}
    </div>
    <div
      style={{
        fontFamily: SANS,
        fontWeight: 700,
        fontSize: 62,
        lineHeight: 1.05,
        color: dark ? COLORS.paper : COLORS.ink,
      }}
    >
      {title}
    </div>
    {support ? (
      <div
        style={{
          fontFamily: SANS,
          fontWeight: 500,
          fontSize: 34,
          color: dark ? "rgba(255,255,255,0.72)" : COLORS.muted,
        }}
      >
        {support}
      </div>
    ) : null}
  </div>
);

export const GreenDot: React.FC<{size?: number}> = ({size = 18}) => (
  <span
    style={{
      display: "inline-block",
      width: size,
      height: size,
      borderRadius: size,
      background: COLORS.green,
    }}
  />
);

export const BrowserFrame: React.FC<{children: React.ReactNode}> = ({
  children,
}) => (
  <div
    style={{
      width: "100%",
      height: "100%",
      display: "flex",
      flexDirection: "column",
      borderRadius: 22,
      overflow: "hidden",
      border: `1px solid ${COLORS.hairline}`,
      boxShadow: "0 40px 120px rgba(13,13,15,0.14)",
      background: COLORS.paper,
    }}
  >
    <div
      style={{
        height: 64,
        flexShrink: 0,
        display: "flex",
        alignItems: "center",
        gap: 18,
        padding: "0 28px",
        borderBottom: `1px solid ${COLORS.hairline}`,
        background: COLORS.paper,
      }}
    >
      <div style={{display: "flex", gap: 10}}>
        {[12, 12, 12].map((size, index) => (
          <span
            key={index}
            style={{
              width: size,
              height: size,
              borderRadius: size,
              background: COLORS.hairline,
            }}
          />
        ))}
      </div>
      <div
        style={{
          flex: 1,
          maxWidth: 760,
          height: 38,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          borderRadius: 10,
          background: "#f4f4f6",
          fontFamily: MONO,
          fontSize: 22,
          color: COLORS.muted,
        }}
      >
        localhost:8000
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          fontFamily: MONO,
          fontSize: 20,
          color: COLORS.muted,
        }}
      >
        <GreenDot size={12} /> live
      </div>
    </div>
    <div style={{flex: 1, minHeight: 0, position: "relative"}}>{children}</div>
  </div>
);

export const screenshot = (name: string): string =>
  staticFile(`screenshots/${name}`);
