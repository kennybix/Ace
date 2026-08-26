import { useRouter } from "expo-router";
import React, { useEffect, useRef, useState } from "react";
import { ActivityIndicator, ScrollView, Text, View } from "react-native";
import QuestionCard from "@/components/QuestionCard";
import { Bar, Button, Card } from "@/components/ui";
import { api, Question } from "@/lib/api";
import { useApp } from "@/lib/store";
import { colors, s, type } from "@/lib/theme";

export default function Diagnostic() {
  const router = useRouter();
  const { examId } = useApp();
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [i, setI] = useState(0);
  const [resumedNote, setResumedNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const completing = useRef(false);

  useEffect(() => {
    if (!examId) return;
    (async () => {
      try {
        const d = await api.diagnosticStart(examId);
        setSessionId(d.session_id);
        if (d.resumed && d.already_answered) {
          setResumedNote(
            `Welcome back — ${d.already_answered} answered, ${d.count} to go.`);
        }
        const qs = await api.questionsBatch(d.question_ids);
        setQuestions(qs.questions);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [examId]);

  if (error) {
    return (
      <View style={[s.screen, { justifyContent: "center" }]}>
        <Card>
          <Text style={type.title}>No questions yet</Text>
          <Text style={[type.body, { marginVertical: 8 }]}>
            Ace needs material to build your baseline. Upload a textbook, syllabus, or past
            questions in the Library — then come back.
          </Text>
          <Button label="Go to Library" onPress={() => router.replace("/(tabs)/library")} />
        </Card>
      </View>
    );
  }

  if (!examId || !sessionId || questions.length === 0) {
    return (
      <View style={[s.screen, { justifyContent: "center", alignItems: "center" }]}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={[type.body, { marginTop: 10 }]}>Building your diagnostic…</Text>
      </View>
    );
  }

  const done = i >= questions.length;
  if (done) {
    if (!completing.current) {
      completing.current = true;  // guard: re-renders must not rebuild the plan repeatedly
      api.diagnosticComplete(examId, sessionId)
        .then(() => router.replace("/(tabs)"))
        .catch((e) => {
          completing.current = false;
          setError((e instanceof Error ? e.message : String(e)).replace(/^\d+: /, ""));
        });
    }
    return (
      <View style={[s.screen, { justifyContent: "center", alignItems: "center" }]}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={[type.body, { marginTop: 10 }]}>
          Scoring… building your plan backwards from exam day.
        </Text>
      </View>
    );
  }

  const q = questions[i];
  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.bg }}
                contentContainerStyle={{ padding: 20, paddingBottom: 32 }}>
      <View style={{ marginBottom: 12 }}>
        <Text style={[type.caption, { marginBottom: 6 }]}>
          BASELINE · {i + 1} OF {questions.length}
        </Text>
        <Bar value={i / questions.length} color={colors.info} height={6} />
        {resumedNote && i === 0 && (
          <Text style={[type.caption, { marginTop: 6, color: colors.primary }]}>
            {resumedNote}
          </Text>
        )}
      </View>
      <QuestionCard
        key={q.id}
        q={q}
        onSubmit={(answer, confidence) =>
          api.submitAttempt({ exam_id: examId, question_id: q.id, session_id: sessionId,
                              answer, confidence })}
        onNext={() => setI(i + 1)}
      />
    </ScrollView>
  );
}
