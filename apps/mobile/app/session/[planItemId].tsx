import { useLocalSearchParams, useRouter } from "expo-router";
import React, { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, Text, View } from "react-native";
import QuestionCard from "@/components/QuestionCard";
import { Bar, Button, Card, Fade } from "@/components/ui";
import { api, SessionStart } from "@/lib/api";
import { useApp } from "@/lib/store";
import { colors, s, type } from "@/lib/theme";

import { Markdown, VideoEmbed } from "@/components/content";

type Stage = "lesson" | "video" | "questions" | "done";

export default function Session() {
  const router = useRouter();
  const { planItemId } = useLocalSearchParams<{ planItemId: string }>();
  const { examId } = useApp();
  const [sess, setSess] = useState<SessionStart | null>(null);
  const [stage, setStage] = useState<Stage>("lesson");
  const [i, setI] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const completing = useRef(false);
  const [reported, setReported] = useState<Set<number>>(new Set());
  const [summary, setSummary] = useState<{ answered: number; correct: number;
                                           streak: { current: number } } | null>(null);

  useEffect(() => {
    api.startSession(Number(planItemId))
      .then((r) => {
        setSess(r);
        if (!r.lesson) setStage(r.video ? "video" : "questions");
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [planItemId]);

  if (error) {
    return (
      <View style={[s.screen, { justifyContent: "center" }]}>
        <Card>
          <Text style={type.title}>Nothing to study here yet</Text>
          <Text style={[type.body, { marginVertical: 8 }]}>{error.replace(/^\d+: /, "")}</Text>
          <Button label="Go to Library" onPress={() => router.replace("/(tabs)/library")} />
        </Card>
      </View>
    );
  }

  if (!sess || !examId) {
    return (
      <View style={[s.screen, { justifyContent: "center", alignItems: "center" }]}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={[type.body, { marginTop: 10 }]}>Preparing your session…</Text>
      </View>
    );
  }

  if (stage === "lesson" && sess.lesson) {
    return (
      <ScrollView style={{ flex: 1, backgroundColor: colors.bg }}
                  contentContainerStyle={{ padding: 20, paddingBottom: 32 }}>
        <Fade>
          <Text style={type.caption}>FIRST, A QUICK READ · 2–3 MIN</Text>
          <Card style={{ marginTop: 8 }}>
            <Markdown body={sess.lesson.body} />
          </Card>
          <View style={{ marginTop: 10 }}>
            <Button label={sess.video ? "Next: watch the video" : "Got it — drill me"}
                    onPress={() => setStage(sess.video ? "video" : "questions")} />
          </View>
        </Fade>
      </ScrollView>
    );
  }

  if (stage === "video" && sess.video) {
    return (
      <ScrollView style={{ flex: 1, backgroundColor: colors.bg }}
                  contentContainerStyle={{ padding: 20, paddingBottom: 32 }}>
        <Fade>
          <Text style={type.caption}>A DIFFERENT EXPLANATION · VETTED FOR THIS TOPIC</Text>
          <Card style={{ marginTop: 8, padding: 8 }}>
            <VideoEmbed youtubeId={sess.video.youtube_id} title={sess.video.title} />
          </Card>
          <View style={{ marginTop: 10 }}>
            <Button label="Got it — drill me" onPress={() => setStage("questions")} />
          </View>
        </Fade>
      </ScrollView>
    );
  }

  if (stage === "questions") {
    if (i >= sess.questions.length) {
      if (!completing.current) {
        completing.current = true;
        api.completeSession(sess.session_id)
          .then((r) => { setSummary(r); setStage("done"); })
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
          <View style={{ flexDirection: "row", justifyContent: "space-between",
                         marginBottom: 6 }}>
            <Text style={type.caption}>QUESTION {i + 1} OF {sess.questions.length}</Text>
          </View>
          <Bar value={i / sess.questions.length} color={colors.primary} height={6} />
        </View>
        <QuestionCard
          key={q.id}
          q={q}
          onSubmit={(answer, confidence) =>
            api.submitAttempt({ exam_id: examId, question_id: q.id,
                                session_id: sess.session_id, answer, confidence })}
          onNext={() => setI(i + 1)}
        />
        <Pressable disabled={reported.has(q.id)}
                   onPress={() => {
                     api.reportQuestion(q.id, "user_flagged");
                     setReported(new Set(reported).add(q.id));
                   }}>
          <Text style={[type.caption, { textAlign: "center", marginTop: 8, marginBottom: 20,
                                        color: reported.has(q.id) ? colors.success
                                          : colors.textFaint }]}>
            {reported.has(q.id) ? "✓ Reported — Ace will review and replace it"
              : "⚑ Report this question"}
          </Text>
        </Pressable>
      </ScrollView>
    );
  }

  return (
    <View style={[s.screen, { justifyContent: "center" }]}>
      <Fade>
        <View style={{ alignItems: "center", marginBottom: 18 }}>
          <Text style={{ fontSize: 56 }}>🎉</Text>
          <Text style={[type.display, { marginTop: 8 }]}>Session complete</Text>
        </View>
        {summary && (
          <Card style={{ alignItems: "center", paddingVertical: 20 }}>
            <Text style={type.stat}>{summary.correct}/{summary.answered} correct</Text>
            <Text style={[type.body, { marginTop: 4 }]}>
              🔥 {summary.streak.current}-day streak · +50 XP
            </Text>
          </Card>
        )}
        <View style={{ marginTop: 10 }}>
          <Button label="Back to Today" onPress={() => router.replace("/(tabs)")} />
        </View>
      </Fade>
    </View>
  );
}
