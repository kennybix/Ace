import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import React from "react";
import { AppProvider } from "@/lib/store";
import { colors } from "@/lib/theme";

export default function RootLayout() {
  return (
    <AppProvider>
      <StatusBar style="light" />
      <Stack screenOptions={{
        headerStyle: { backgroundColor: colors.bg },
        headerTintColor: colors.text,
        headerShadowVisible: false,
        contentStyle: { backgroundColor: colors.bg },
      }}>
        <Stack.Screen name="index" options={{ headerShown: false }} />
        <Stack.Screen name="login" options={{ headerShown: false }} />
        <Stack.Screen name="onboarding" options={{ headerShown: false }} />
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="session/[planItemId]" options={{ title: "Session" }} />
        <Stack.Screen name="topics" options={{ title: "Syllabus topics" }} />
        <Stack.Screen name="topic/[topicId]" options={{ title: "Topic" }} />
        <Stack.Screen name="drill/[sessionId]" options={{ title: "Topic drill" }} />
        <Stack.Screen name="diagnostic" options={{ title: "Diagnostic" }} />
        <Stack.Screen name="mock" options={{ title: "Mock exam" }} />
        <Stack.Screen name="flashcards" options={{ title: "Flashcards" }} />
      </Stack>
    </AppProvider>
  );
}
