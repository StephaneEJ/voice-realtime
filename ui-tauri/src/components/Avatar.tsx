// Persona avatar — circular tint background + initial. Sizes echo the
// `.mf-av.<sm|md|lg|xl|xxl>` class system in midfi.css.

const SIZES = {
  sm: 22,
  md: 32,
  lg: 48,
  xl: 80,
  xxl: 112,
} as const;

const PERSONA_TINTS: Record<string, string> = {
  aria: "#ff8a7a",
  koda: "#4fc3f7",
  mira: "#c084fc",
  noor: "#5eead4",
  zen: "#a3e635",
  fox: "#ffb74d",
  jarvis: "#4fc3f7",
  hormozi: "#ffb74d",
  "coach-halt": "#5eead4",
};

export interface AvatarProps {
  personaId: string;
  size?: keyof typeof SIZES;
  live?: boolean;
}

export function Avatar({ personaId, size = "md", live = false }: AvatarProps) {
  const px = SIZES[size];
  const tint = PERSONA_TINTS[personaId.toLowerCase()] ?? "#4fc3f7";
  const initial = personaId.trim().charAt(0).toUpperCase() || "?";
  const fontSize = Math.round(px * 0.42);

  return (
    <div
      style={{
        width: px,
        height: px,
        borderRadius: "50%",
        background: `radial-gradient(circle at 30% 30%, ${tint}, ${tint}AA)`,
        color: "rgba(0,0,0,0.7)",
        fontFamily: "var(--mf-display)",
        fontWeight: 600,
        fontSize,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        position: "relative",
        boxShadow: live
          ? `0 0 0 2px var(--mf-bg), 0 0 0 3px ${tint}, 0 0 24px ${tint}55`
          : "0 1px 0 rgba(255,255,255,0.06) inset",
        flexShrink: 0,
      }}
    >
      {initial}
      {live ? (
        <span
          style={{
            position: "absolute",
            inset: 0,
            borderRadius: "50%",
            border: `1px solid ${tint}`,
            animation: "mf-pulse 1.6s ease-out infinite",
          }}
        />
      ) : null}
    </div>
  );
}
