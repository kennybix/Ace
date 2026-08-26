import { useFocusEffect, useRouter } from "expo-router";
import React, { useCallback, useState } from "react";
import { Text, View } from "react-native";
import { Button, Card, Fade, LabeledBar, Screen, Section } from "@/components/ui";
import { api, Readiness } from "@/lib/api";
import { useApp } from "@/lib/store";
import { colors, type } from "@/lib/theme";

const SIGNAL_LABEL: Record<string, string> = {
  accuracy: "Drill accuracy", mock: "Mock score", calibration: "Confidence calibration",
  recall: "Spaced recall",
};

export default function ReadinessScreen() {
  const router = useRouter();
  const { examId } = useApp();
  const [r, setR] = useState<Readiness | null>(null);

  useFocusEffect(useCallback(() => {
    if (!examId) return;
    api.readiness(examId).then(setR).catch(() => null);
  }, [examId]));

  const pct = r ? Math.round(r.composite * 100) : 0;
  const tone = pct >= 70 ? colors.success : pct >= 45 ? colors.primary : colors.danger;

  return (
    <Screen title="Readiness" subtitle="A composite of every signal Ace tracks">
      {!r ? (
        <Card><Text style={type.body}>Complete a session and this comes alive.</Text></Card>
      ) : (
        <>
          <Fade>
            <Card style={{ alignItems: "center", paddingVertical: 26 }}>
              <View style={{ width: 132, height: 132, borderRadius: 66, borderWidth: 8,
                             borderColor: tone, alignItems: "center",
                             justifyContent: "center", backgroundColor: colors.surfaceRaised }}>
                <Text style={[type.display, { fontSize: 40 }]}>{pct}%</Text>
              </View>
              <Text style={[type.caption, { marginTop: 12 }]}>
                from {Object.keys(r.signals).length} live signal
                {Object.keys(r.signals).length === 1 ? "" : "s"}
              </Text>
            </Card>
          </Fade>

          <Fade delay={80}>
            <Section title="Signals" />
            <Card>
              {Object.entries(r.signals).map(([k, v]) => (
                <LabeledBar key={k} label={SIGNAL_LABEL[k] ?? k} value={v} />
              ))}
            </Card>

            <Section title={`Elements (${r.elements?.length ?? 0})`} />
            <Card>
              {(r.elements ?? []).map((t) => (
                <LabeledBar key={t.code} label={`${t.code}. ${t.title}`} value={t.mastery} />
              ))}
            </Card>

            {Object.keys(r.per_format).length > 1 && (
              <>
                <Section title="By question format" />
                <Card>
                  {Object.entries(r.per_format).map(([f, v]) => (
                    <LabeledBar key={f} label={`${f.toUpperCase()} · ${v.n} answered`}
                                value={v.accuracy} />
                  ))}
                </Card>
              </>
            )}

            <Section title="Test yourself" />
            <Card>
              <Text style={type.body}>
                A timed, exam-weighted mock — anytime, not just at plan milestones. The score
                feeds your readiness.
              </Text>
              <View style={{ marginTop: 10, gap: 8 }}>
                <Button label="⚔️  Start a practice mock" variant="secondary"
                        onPress={() => router.push("/mock")} />
                <Button label="🃏  Flashcard sprint (weakest topics)" variant="secondary"
                        onPress={() => router.push("/flashcards")} />
              </View>
            </Card>
          </Fade>
        </>
      )}
    </Screen>
  );
}
