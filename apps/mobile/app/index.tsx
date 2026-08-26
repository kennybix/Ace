import { Redirect } from "expo-router";
import React, { useEffect, useState } from "react";
import { ActivityIndicator, View } from "react-native";
import { api } from "@/lib/api";
import { useApp } from "@/lib/store";
import { colors, s } from "@/lib/theme";

export default function Index() {
  const { token, examId, restoring, setExamId } = useApp();
  const [examChecked, setExamChecked] = useState(false);

  // Signed in but no exam selected (fresh install or re-login): look up existing exams
  useEffect(() => {
    if (restoring || !token || examId) return;
    api.listExams()
      .then((r) => { if (r.exams[0]) setExamId(r.exams[0].id); })
      .catch(() => null)
      .finally(() => setExamChecked(true));
  }, [restoring, token, examId]);

  if (restoring || (token && !examId && !examChecked)) {
    return (
      <View style={[s.screen, { justifyContent: "center", alignItems: "center" }]}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }
  if (!token) return <Redirect href="/login" />;
  if (!examId) return <Redirect href="/onboarding" />;
  return <Redirect href="/(tabs)" />;
}
