import { useRouter } from "expo-router";
import React, { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, Text, View } from "react-native";
import QuestionCard from "@/components/QuestionCard";
import { Bar, Button, Card, Fade, LabeledBar } from "@/components/ui";
import { api, Question } from "@/lib/api";
import { useApp } from "@/lib/store";
import { colors, radius, s, type } from "@/lib/theme";

export default function Mock() {
  const router = useRouter();
  const { examId } = useApp();
  const [mockId, setMockId] = useState<number | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [i, setI] = useState(0);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [report, setReport] = useState<{ score: number;
                                         per_element: Record<string, number> } | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!examId) return;
    api.startMock(examId)
      .then((r) => {
        setMockId(r.mock_id);
        setQuestions(r.questions);
        setSecondsLeft(r.duration_min * 60);
        timer.current = setInterval(() => setSecondsLeft((x) => Math.max(x - 1, 0)), 1000);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [examId]);

  const submit = async () => {
    if (!examId || !mockId) return;
    if (timer.current) clearInterval(timer.current);
    setReport(await api.submitMock(examId, mockId));
  };

  useEffect(() => {
    if (secondsLeft === 0 && mockId && !report && questions.length) submit();
  }, [secondsLeft]);

  if (error) {
    return (
      <View style={[s.screen, { justifyContent: "center" }]}>
        <Card>
          <Text style={type.title}>Can't assemble a mock yet</Text>
          <Text style={[type.body, { marginVertical: 8 }]}>{error.replace(/^\d+: /, "")}</Text>
          <Button label="Back" onPress={() => router.replace("/(tabs)")} />
        </Card>
      </View>
    );
  }

  if (!examId || !mockId) {
    return (
      <View style={[s.screen, { justifyContent: "center", alignItems: "center" }]}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={[type.body, { marginTop: 10 }]}>Assembling your paper…</Text>
      </View>
    );
  }

  if (report) {
    const pct = Math.round(report.score * 100);
    const passed = report.score >= 0.6;
    return (
      <ScrollView style={{ flex: 1, backgroundColor: colors.bg }}
                  contentContainerStyle={{ padding: 20, paddingBottom: 32 }}>
        <Fade>
          <Card style={{ alignItems: "center", paddingVertical: 26 }}
                tone={passed ? "success" : "danger"}>
            <Text style={type.caption}>{passed ? "BOSS DEFEATED" : "REMATCH NEEDED"}</Text>
            <Text style={[type.display, { fontSize: 52, marginVertical: 6,
                                          color: passed ? colors.success : colors.danger }]}>
              {pct}%
            </Text>
            <Text style={type.body}>{passed ? "That's a pass-level score."
              : "Below the 60% bar — the plan adapts tonight."}</Text>
          </Card>
          <Card>
            {Object.entries(report.per_element).map(([code, v]) => (
              <LabeledBar key={code} label={`Element ${code}`} value={v} />
            ))}
          </Card>
          <View style={{ marginTop: 10 }}>
            <Button label="Back to Today" onPress={() => router.replace("/(tabs)")} />
          </View>
        </Fade>
      </ScrollView>
    );
  }

  const mm = String(Math.floor(secondsLeft / 60)).padStart(2, "0");
  const ss = String(secondsLeft % 60).padStart(2, "0");

  if (i >= questions.length) {
    return (
      <View style={[s.screen, { justifyContent: "center" }]}>
        <Card style={{ alignItems: "center", paddingVertical: 24 }}>
          <Text style={type.title}>All {questions.length} answered</Text>
          <Text style={[type.body, { marginVertical: 8 }]}>Time left: {mm}:{ss}</Text>
        </Card>
        <Button label="Submit mock" onPress={submit} />
      </View>
    );
  }

  const q = questions[i];
  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.bg }}
                contentContainerStyle={{ padding: 20, paddingBottom: 32 }}>
      <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 12, gap: 12 }}>
        <View style={{ flex: 1 }}>
          <Text style={[type.caption, { marginBottom: 6 }]}>
            {i + 1} OF {questions.length}
          </Text>
          <Bar value={i / questions.length} color={colors.warning} height={6} />
        </View>
        <View style={{ backgroundColor: secondsLeft < 300 ? colors.dangerBg
                         : colors.surfaceRaised,
                       borderRadius: radius.pill, paddingVertical: 6, paddingHorizontal: 12,
                       borderWidth: 1,
                       borderColor: secondsLeft < 300 ? "rgba(240,113,113,0.4)"
                         : colors.border }}>
          <Text style={{ color: secondsLeft < 300 ? colors.danger : colors.text,
                         fontWeight: "700", fontVariant: ["tabular-nums"] }}>
            ⏱ {mm}:{ss}
          </Text>
        </View>
      </View>
      <QuestionCard
        key={q.id}
        q={q}
        hideConfidence
        onSubmit={(answer) =>
          api.submitAttempt({ exam_id: examId, question_id: q.id, mock_id: mockId, answer })}
        onNext={() => setI(i + 1)}
      />
      <Pressable onPress={submit}>
        <Text style={[type.caption, { textAlign: "center", marginTop: 8, marginBottom: 20 }]}>
          Finish early & submit
        </Text>
      </Pressable>
    </ScrollView>
  );
}
