import { LinearGradient } from "expo-linear-gradient";
import React, { useEffect, useRef } from "react";
import {
  ActivityIndicator, Animated, Pressable, ScrollView, StyleProp, Text, View, ViewStyle,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, gradients, radius, type } from "@/lib/theme";

/* ---------- Screen: safe-area padding, display header, optional scroll ---------- */
export function Screen({ title, subtitle, children, scroll = true, right }: {
  title?: string; subtitle?: string; children: React.ReactNode; scroll?: boolean;
  right?: React.ReactNode;
}) {
  const insets = useSafeAreaInsets();
  const inner = (
    <>
      {title && (
        <View style={{ marginBottom: 16, flexDirection: "row", alignItems: "flex-end" }}>
          <View style={{ flex: 1 }}>
            <Text style={type.display}>{title}</Text>
            {subtitle ? <Text style={[type.body, { marginTop: 4 }]}>{subtitle}</Text> : null}
          </View>
          {right}
        </View>
      )}
      {children}
    </>
  );
  const base: StyleProp<ViewStyle> = {
    flex: 1, backgroundColor: colors.bg,
  };
  if (!scroll) {
    return <View style={[base, { padding: 20, paddingTop: insets.top + 16 }]}>{inner}</View>;
  }
  return (
    <ScrollView style={base}
                contentContainerStyle={{ padding: 20, paddingTop: insets.top + 16,
                                         paddingBottom: 32 }}>
      {inner}
    </ScrollView>
  );
}

/* ---------- Entrance animation ---------- */
export function Fade({ delay = 0, children }: { delay?: number; children: React.ReactNode }) {
  const v = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(v, { toValue: 1, duration: 420, delay, useNativeDriver: true }).start();
  }, [v, delay]);
  return (
    <Animated.View style={{
      opacity: v,
      transform: [{ translateY: v.interpolate({ inputRange: [0, 1], outputRange: [10, 0] }) }],
    }}>
      {children}
    </Animated.View>
  );
}

/* ---------- Card ---------- */
export function Card({ children, style, tone }: {
  children: React.ReactNode; style?: StyleProp<ViewStyle>;
  tone?: "default" | "success" | "danger" | "primary";
}) {
  const bg = tone === "success" ? colors.successBg : tone === "danger" ? colors.dangerBg
    : tone === "primary" ? colors.primaryBg : colors.surface;
  const border = tone === "success" ? "rgba(95,195,119,0.35)"
    : tone === "danger" ? "rgba(240,113,113,0.35)"
    : tone === "primary" ? "rgba(163,217,119,0.35)" : colors.border;
  return (
    <View style={[{ backgroundColor: bg, borderRadius: radius.lg, padding: 16,
                    marginVertical: 6, borderWidth: 1, borderColor: border }, style]}>
      {children}
    </View>
  );
}

/* ---------- Buttons ---------- */
export function Button({ label, onPress, variant = "primary", disabled, loading, small }: {
  label: string; onPress: () => void; variant?: "primary" | "secondary" | "ghost" | "danger";
  disabled?: boolean; loading?: boolean; small?: boolean;
}) {
  const inactive = disabled || loading;
  const inner = (pressed: boolean) => (
    <View style={{ alignItems: "center", justifyContent: "center",
                   paddingVertical: small ? 10 : 15, paddingHorizontal: small ? 14 : 20,
                   opacity: pressed ? 0.85 : 1 }}>
      {loading ? (
        <ActivityIndicator color={variant === "primary" ? colors.primaryFg : colors.text} />
      ) : (
        <Text style={{
          fontWeight: "700", fontSize: small ? 14 : 16,
          color: variant === "primary" ? colors.primaryFg
            : variant === "danger" ? colors.danger : colors.text,
        }}>{label}</Text>
      )}
    </View>
  );
  if (variant === "primary") {
    return (
      <Pressable onPress={onPress} disabled={inactive}
                 style={({ pressed }) => ({ opacity: inactive ? 0.45 : 1,
                                            transform: [{ scale: pressed ? 0.98 : 1 }] })}>
        <LinearGradient colors={gradients.primary} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
                        style={{ borderRadius: radius.md }}>
          {inner(false)}
        </LinearGradient>
      </Pressable>
    );
  }
  return (
    <Pressable onPress={onPress} disabled={inactive}
               style={({ pressed }) => ({
                 borderRadius: radius.md,
                 backgroundColor: variant === "ghost" ? "transparent" : colors.surfaceRaised,
                 borderWidth: variant === "ghost" ? 0 : 1,
                 borderColor: variant === "danger" ? "rgba(240,113,113,0.4)" : colors.border,
                 opacity: inactive ? 0.45 : 1,
                 transform: [{ scale: pressed ? 0.98 : 1 }],
               })}>
      {({ pressed }) => inner(pressed)}
    </Pressable>
  );
}

/* ---------- Chip (selectable pill) ---------- */
export function Chip({ label, selected, onPress, flex }: {
  label: string; selected?: boolean; onPress?: () => void; flex?: boolean;
}) {
  return (
    <Pressable onPress={onPress}
               style={({ pressed }) => ({
                 paddingVertical: 10, paddingHorizontal: 16, borderRadius: radius.pill,
                 backgroundColor: selected ? colors.primary : colors.surfaceRaised,
                 borderWidth: 1, borderColor: selected ? colors.primary : colors.border,
                 alignItems: "center", flex: flex ? 1 : undefined,
                 transform: [{ scale: pressed ? 0.96 : 1 }],
               })}>
      <Text style={{ color: selected ? colors.primaryFg : colors.text, fontWeight: "600",
                     fontSize: 13.5 }}>{label}</Text>
    </Pressable>
  );
}

/* ---------- Progress bar ---------- */
export function Bar({ value, color, height = 8 }: { value: number; color?: string;
                                                    height?: number }) {
  const c = color ?? (value >= 0.7 ? colors.success : value >= 0.45 ? colors.primary
    : colors.danger);
  return (
    <View style={{ height, backgroundColor: colors.surfaceRaised, borderRadius: height / 2,
                   overflow: "hidden" }}>
      <View style={{ height, width: `${Math.round(Math.min(Math.max(value, 0), 1) * 100)}%`,
                     backgroundColor: c, borderRadius: height / 2 }} />
    </View>
  );
}

export function LabeledBar({ label, value, right }: { label: string; value: number;
                                                      right?: string }) {
  return (
    <View style={{ marginVertical: 6 }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: 5 }}>
        <Text style={[type.caption, { color: colors.textMuted, flex: 1 }]} numberOfLines={1}>
          {label}
        </Text>
        <Text style={type.caption}>{right ?? `${Math.round(value * 100)}%`}</Text>
      </View>
      <Bar value={value} />
    </View>
  );
}

/* ---------- Stat tile ---------- */
export function Stat({ value, label, accent }: { value: string; label: string;
                                                 accent?: boolean }) {
  return (
    <View style={{ flex: 1, backgroundColor: colors.surface, borderRadius: radius.lg,
                   borderWidth: 1, borderColor: colors.border, paddingVertical: 14,
                   alignItems: "center" }}>
      <Text style={[type.stat, accent && { color: colors.primary }]}>{value}</Text>
      <Text style={[type.caption, { marginTop: 2 }]}>{label}</Text>
    </View>
  );
}

/* ---------- Section header ---------- */
export function Section({ title, style }: { title: string; style?: StyleProp<ViewStyle> }) {
  return (
    <View style={[{ marginTop: 20, marginBottom: 6 }, style]}>
      <Text style={{ color: colors.textFaint, fontSize: 13, fontWeight: "700",
                     textTransform: "uppercase", letterSpacing: 1 }}>{title}</Text>
    </View>
  );
}

/* ---------- Connection pill ---------- */
export function ConnPill({ state, detail, onRetry }: {
  state: "checking" | "ok" | "down"; detail?: string; onRetry?: () => void;
}) {
  const dot = state === "ok" ? colors.success : state === "down" ? colors.danger
    : colors.warning;
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 8,
                   backgroundColor: colors.surface, borderRadius: radius.pill,
                   borderWidth: 1, borderColor: colors.border,
                   paddingVertical: 8, paddingHorizontal: 14, alignSelf: "flex-start" }}>
      <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: dot }} />
      <Text style={[type.caption, { color: colors.textMuted }]} numberOfLines={1}>
        {state === "ok" ? `Connected · ${detail}` : state === "checking" ? "Connecting…"
          : "Server unreachable — check Tailscale or Wi-Fi"}
      </Text>
      {state === "down" && onRetry && (
        <Pressable onPress={onRetry}>
          <Text style={[type.caption, { color: colors.primary, fontWeight: "700" }]}>Retry</Text>
        </Pressable>
      )}
    </View>
  );
}
