/* Ace design tokens — semantic, dark-first, lime-on-deep-navy brand.
   Structure mirrors the house design-system style (background/surface/primary/muted/…). */

export const colors = {
  bg: "#0A0F1A",            // deep navy — app background
  surface: "#101828",       // cards
  surfaceRaised: "#16203a", // elevated cards / inputs
  border: "#1E2A42",
  text: "#F5F8FC",
  textMuted: "#8FA0B5",
  textFaint: "#5C6B80",

  primary: "#A3D977",       // Ace lime
  primaryDark: "#7CB342",
  primaryFg: "#0B1A05",     // text on primary
  info: "#6C9EF2",
  success: "#5FC377",
  danger: "#F07171",
  warning: "#F2C14E",

  successBg: "rgba(95,195,119,0.12)",
  dangerBg: "rgba(240,113,113,0.12)",
  primaryBg: "rgba(163,217,119,0.12)",
};

export const gradients = {
  primary: ["#A3D977", "#5FB865"] as const,
  hero: ["#152036", "#101828"] as const,
};

export const radius = { sm: 8, md: 12, lg: 16, xl: 20, pill: 999 };

export const space = (n: number) => n * 4;

export const type = {
  display: { fontSize: 30, fontWeight: "800" as const, color: colors.text, letterSpacing: -0.5 },
  title: { fontSize: 20, fontWeight: "700" as const, color: colors.text, letterSpacing: -0.3 },
  subtitle: { fontSize: 16, fontWeight: "600" as const, color: colors.text },
  body: { fontSize: 15, fontWeight: "400" as const, color: colors.textMuted, lineHeight: 22 },
  bodyStrong: { fontSize: 15, fontWeight: "600" as const, color: colors.text, lineHeight: 22 },
  caption: { fontSize: 12.5, fontWeight: "500" as const, color: colors.textFaint },
  stat: { fontSize: 24, fontWeight: "800" as const, color: colors.text, letterSpacing: -0.5 },
};

/* Legacy shortcut styles kept for incremental migration */
export const s = {
  screen: { flex: 1, backgroundColor: colors.bg, padding: 20 } as const,
  h1: type.display,
  h2: type.title,
  p: type.body,
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: 16,
    marginVertical: 6,
    borderWidth: 1,
    borderColor: colors.border,
  } as const,
  btn: {
    backgroundColor: colors.primary,
    borderRadius: radius.md,
    padding: 15,
    alignItems: "center" as const,
  },
  btnText: { color: colors.primaryFg, fontWeight: "700" as const, fontSize: 16 },
  input: {
    backgroundColor: colors.surfaceRaised,
    color: colors.text,
    borderRadius: radius.md,
    padding: 14,
    marginVertical: 6,
    borderWidth: 1,
    borderColor: colors.border,
    fontSize: 16,
  } as const,
};
