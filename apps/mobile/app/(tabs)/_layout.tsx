import { Redirect, Tabs } from "expo-router";
import React from "react";
import { Text } from "react-native";
import { useApp } from "@/lib/store";
import { colors } from "@/lib/theme";

function Icon({ glyph, color, focused }: { glyph: string; color: string; focused: boolean }) {
  return <Text style={{ fontSize: 20, color, opacity: focused ? 1 : 0.75 }}>{glyph}</Text>;
}

export default function TabsLayout() {
  const { token, restoring } = useApp();
  if (!restoring && !token) return <Redirect href="/login" />;
  return (
    <Tabs screenOptions={{
      headerShown: false,
      tabBarStyle: {
        backgroundColor: colors.surface,
        borderTopColor: colors.border,
        borderTopWidth: 1,
        height: 62,
        paddingTop: 6,
        paddingBottom: 8,
      },
      tabBarActiveTintColor: colors.primary,
      tabBarInactiveTintColor: colors.textFaint,
      tabBarLabelStyle: { fontSize: 11, fontWeight: "600" },
      sceneStyle: { backgroundColor: colors.bg },
    }}>
      <Tabs.Screen name="index" options={{ title: "Today",
        tabBarIcon: (p) => <Icon glyph="◎" {...p} /> }} />
      <Tabs.Screen name="plan" options={{ title: "Plan",
        tabBarIcon: (p) => <Icon glyph="🧭" {...p} /> }} />
      <Tabs.Screen name="library" options={{ title: "Library",
        tabBarIcon: (p) => <Icon glyph="📚" {...p} /> }} />
      <Tabs.Screen name="readiness" options={{ title: "Readiness",
        tabBarIcon: (p) => <Icon glyph="📈" {...p} /> }} />
      <Tabs.Screen name="profile" options={{ title: "Profile",
        tabBarIcon: (p) => <Icon glyph="👤" {...p} /> }} />
    </Tabs>
  );
}
