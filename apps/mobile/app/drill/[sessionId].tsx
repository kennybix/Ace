import { useLocalSearchParams, useRouter } from "expo-router";
import React, { useEffect, useRef, useState } from "react";
import { ActivityIndicator, ScrollView, Text, View } from "react-native";
import QuestionCard from "@/components/QuestionCard";
import { Bar, Button, Card, Fade } from "@/components/ui";
import { api, SessionStart } from "@/lib/api";
import { useApp } from "@/lib/store";
import { colors, s, type } from "@/lib/theme";

export default function Drill() {
  const router = useRouter();
  const { sessionId } = useLocalSearchParams<{ sessionId: string }>();
  const { examId, restoring, token } = useApp();
  const [sess, setSess] = useState<SessionStart | null>(null);
  const [i, setI] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const completing = useRef(false);
  const [summary, setSummary] = useState<{ answered: number; correct: number } | null>(null);

  useEffect(() => {
    if (restoring || !token) return;  // deep links arrive before the stored session loads
    api.openSession(Number(sessionId))
      .then(setSess)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [sessionId, restoring, token]);

  if (error) {
    return (
      <View style={[s.screen, { justifyContent: "center" }]}>
        <Card>
          <Text style={type.title}>Couldn't open this drill</Text>
          <Text style={[type.body, { marginVertical: 8 }]}>{error.replace(/^\d+: /, "")}</Text>
          <Button label="Back" onPress={() => router.back()} />
        </Card>
      </View>
    );
  }

  if (!sess || !examId) {
    return (
      <View style={[s.screen, { justifyContent: "center", alignItems: "center" }]}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  if (summary) {
    return (
      <View style={[s.screen, { justifyContent: "center" }]}>
        <Fade>
          <Card style={{ alignItems: "center", paddingVertical: 22 }}>
            <Text style={{ fontSize: 44 }}>🎯</Text>
            <Text style={[type.title, { marginTop: 6 }]}>
              {summary.correct}/{summary.answered} correct
            </Text>
            <Text style={type.body}>Drill complete — mastery updated.</Text>
          </Card>
          <Button label="Done" onPress={() => router.back()} />
        </Fade>
      </View>
    );
  }

  if (i >= sess.questions.length) {
    if (!completing.current) {
      completing.current = true;
      api.completeSession(sess.session_id)
        .then((r) => setSummary({ answered: r.answered, correct: r.correct }))
        .catch((e) => {
          completing.current = false;
          setError((e instanceof Error ? e.message : String(e)).replace(/^\d+: /, ""));
        });
    }
    return (
      <View style={[s.screen, { justifyContent: "center", alignItems: "center" }]}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  const q = sess.questions[i];
  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.bg }}
                contentContainerStyle={{ padding: 20, paddingBottom: 32 }}>
      <View style={{ marginBottom: 12 }}>
        <Text style={[type.caption, { marginBottom: 6 }]}>
          TOPIC DRILL · {i + 1} OF {sess.questions.length}
        </Text>
        <Bar value={i / sess.questions.length} height={6} />
      </View>
      <QuestionCard
        key={q.id}
        q={q}
        onSubmit={(answer, confidence) =>
          api.submitAttempt({ exam_id: examId, question_id: q.id,
                              session_id: sess.session_id, answer, confidence })}
        onNext={() => setI(i + 1)}
      />
    </ScrollView>
  );
}
