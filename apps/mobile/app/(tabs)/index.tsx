import { LinearGradient } from "expo-linear-gradient";
import { useFocusEffect, useRouter } from "expo-router";
import React, { useCallback, useState } from "react";
import { Text, View } from "react-native";
import { Button, Card, Fade, Screen, Stat } from "@/components/ui";
import { api, Gamify, PlanItem } from "@/lib/api";
import { useApp } from "@/lib/store";
import { colors, gradients, radius, type } from "@/lib/theme";

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export default function Today() {
  const router = useRouter();
  const { examId } = useApp();
  const [item, setItem] = useState<PlanItem | null>(null);
  const [next, setNext] = useState<PlanItem | null>(null);
  const [g, setG] = useState<Gamify | null>(null);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [exam, setExam] = useState<{ name_raw: string; exam_date: string | null;
    counts: { topics: number; questions: number } } | null>(null);

  useFocusEffect(useCallback(() => {
    if (!examId) return;
    api.getPlan(examId)
      .then(() => {
        setNeedsSetup(false);
        return api.todayItem(examId).then(async (r) => {
          setItem(r.item);
          if (!r.item) setNext((await api.nextItem(examId)).item);
        });
      })
      .catch(() => { setNeedsSetup(true); setItem(null); });
    api.gamify().then(setG).catch(() => null);
    api.getExam(examId).then(setExam).catch(() => null);
  }, [examId]));

  // local-midnight arithmetic — new Date("YYYY-MM-DD") is UTC and drifts a day in the evening
  const daysLeft = exam?.exam_date
    ? (() => {
        const [y, m, d] = exam.exam_date.split("-").map(Number);
        const target = new Date(y, m - 1, d).getTime();
        const today0 = new Date().setHours(0, 0, 0, 0);
        return Math.max(0, Math.round((target - today0) / 86400000));
      })()
    : null;

  return (
    <Screen title={greeting()}
            subtitle={exam
              ? `${exam.name_raw}${daysLeft !== null ? ` · ${daysLeft} days to exam day` : ""}`
              : undefined}>
      {g && (
        <Fade>
          <View style={{ flexDirection: "row", gap: 8 }}>
            <Stat value={`${g.streak.current}`} label="day streak" accent />
            <Stat value={`${g.xp}`} label="XP" />
            <Stat value={`${g.level}`} label="level" />
          </View>
        </Fade>
      )}

      <Fade delay={100}>
        {needsSetup && (
          <Card tone="primary" style={{ marginTop: 16 }}>
            <Text style={type.title}>One step left: your baseline</Text>
            <Text style={[type.body, { marginVertical: 8 }]}>
              Your environment is ready
              {exam ? ` — ${exam.counts.topics} topics and ${exam.counts.questions} questions loaded` : ""}
              . Take the short diagnostic so Ace can build your plan backwards from exam day.
            </Text>
            <Button label="Take the diagnostic" onPress={() => router.push("/diagnostic")} />
          </Card>
        )}

        {item && (
          <LinearGradient colors={gradients.hero} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
                          style={{ borderRadius: radius.xl, padding: 18, marginTop: 16,
                                   borderWidth: 1, borderColor: colors.border }}>
            <Text style={type.caption}>TODAY'S QUEST</Text>
            <Text style={[type.title, { marginTop: 6 }]}>
              {item.kind === "mock" ? "⚔️  Boss fight: full mock exam"
                : item.kind === "taper" ? "🎯  Taper: high-yield revision"
                : `📘  Study session${item.topic_codes?.length
                    ? ` · ${item.topic_codes.slice(0, 3).join(", ")}` : ""}`}
            </Text>
            <Text style={[type.body, { marginTop: 4, marginBottom: 14 }]}>
              ~{item.est_minutes} min · {item.day}
            </Text>
            <Button label={item.kind === "mock" ? "Enter the exam hall" : "Start"}
                    onPress={() =>
                      item.kind === "mock" ? router.push("/mock")
                        : router.push({ pathname: "/session/[planItemId]",
                                        params: { planItemId: String(item.id) } })} />
          </LinearGradient>
        )}

        {!item && !needsSetup && (
          <Card style={{ marginTop: 16, alignItems: "center", paddingVertical: 24 }}>
            <Text style={{ fontSize: 34 }}>🌙</Text>
            <Text style={[type.subtitle, { marginTop: 8 }]}>Nothing due today</Text>
            <Text style={[type.body, { textAlign: "center", marginTop: 4 }]}>
              {next ? `Next up: ${next.kind === "mock" ? "mock exam" : "study session"} on ${next.day}.`
                : "Rest is part of the plan too."}
            </Text>
            {next && next.kind !== "mock" && (
              <View style={{ marginTop: 12, alignSelf: "stretch" }}>
                <Button label="Feeling keen? Start it early" variant="secondary"
                        onPress={() =>
                          router.push({ pathname: "/session/[planItemId]",
                                        params: { planItemId: String(next.id) } })} />
              </View>
            )}
          </Card>
        )}
      </Fade>
    </Screen>
  );
}
