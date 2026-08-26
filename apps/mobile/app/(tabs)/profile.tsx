import { useFocusEffect, useRouter } from "expo-router";
import React, { useCallback, useState } from "react";
import { Alert, Pressable, Text, View } from "react-native";
import { Button, Card, Chip, Fade, Screen, Section } from "@/components/ui";
import { api, Gamify } from "@/lib/api";
import { clearDailyReminder, getReminderHour, setDailyReminder } from "@/lib/reminders";
import { useApp } from "@/lib/store";
import { colors, radius, type } from "@/lib/theme";

type ExamRow = { id: number; name_raw: string; status: string; exam_date: string | null };

export default function Profile() {
  const router = useRouter();
  const { email, signOut, examId, setExamId } = useApp();
  const [g, setG] = useState<Gamify | null>(null);
  const [models, setModels] = useState<{ id: string; label: string }[]>([]);
  const [selected, setSelected] = useState("");
  const [exams, setExams] = useState<ExamRow[]>([]);
  const [reminderHour, setReminderHour] = useState<number | null>(null);

  useFocusEffect(useCallback(() => {
    getReminderHour().then(setReminderHour).catch(() => null);
    api.gamify().then(setG).catch(() => null);
    api.listModels().then((r) => { setModels(r.models); setSelected(r.selected); })
      .catch(() => null);
    api.listExams().then((r) => setExams(r.exams)).catch(() => null);
  }, []));

  return (
    <Screen title="Profile" subtitle={email ?? undefined}>
      <Fade>
        <Section title="My exams" style={{ marginTop: 0 }} />
        <Card style={{ padding: 6 }}>
          {exams.map((e, i) => (
            <Pressable key={e.id} onPress={() => setExamId(e.id)}
                       style={({ pressed }) => ({
                         flexDirection: "row", alignItems: "center", padding: 12,
                         borderRadius: radius.sm,
                         backgroundColor: pressed ? colors.surfaceRaised : "transparent",
                         borderTopWidth: i === 0 ? 0 : 1, borderTopColor: colors.border,
                       })}>
              <View style={{ width: 18, height: 18, borderRadius: 9, borderWidth: 2,
                             marginRight: 12,
                             borderColor: examId === e.id ? colors.primary : colors.textFaint,
                             alignItems: "center", justifyContent: "center" }}>
                {examId === e.id && (
                  <View style={{ width: 8, height: 8, borderRadius: 4,
                                 backgroundColor: colors.primary }} />
                )}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={type.bodyStrong}>{e.name_raw}</Text>
                <Text style={type.caption}>
                  {e.exam_date ? `Exam day ${e.exam_date}` : "No date set"}
                  {examId === e.id ? " · active" : ""}
                </Text>
              </View>
            </Pressable>
          ))}
        </Card>
        <View style={{ marginTop: 8 }}>
          <Button label="＋ Prepare for another exam" variant="secondary"
                  onPress={() => router.push("/onboarding")} />
        </View>
      </Fade>

      {g && (
        <Fade delay={60}>
          <Section title="Progress" />
          <Card>
            <Text style={type.bodyStrong}>
              Level {g.level} · {g.xp} XP · streak {g.streak.current} (best {g.streak.best})
            </Text>
          </Card>
          <Section title="Badges" />
          {g.badges.length === 0 ? (
            <Card><Text style={type.body}>None yet — today's session awaits.</Text></Card>
          ) : (
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
              {g.badges.map((b) => (
                <View key={b.key}
                      style={{ backgroundColor: colors.surface, borderRadius: radius.pill,
                               borderWidth: 1, borderColor: colors.border,
                               paddingVertical: 8, paddingHorizontal: 14 }}>
                  <Text style={{ color: colors.primary, fontSize: 13, fontWeight: "600" }}>
                    🏅 {b.label}
                  </Text>
                </View>
              ))}
            </View>
          )}
        </Fade>
      )}

      <Fade delay={90}>
        <Section title="Daily reminder" />
        <Text style={[type.caption, { marginBottom: 8 }]}>
          A nudge when your session is ready. Streaks live and die by this.
        </Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          <Chip label="Off" selected={reminderHour === null}
                onPress={async () => { await clearDailyReminder(); setReminderHour(null); }} />
          {[[7, "7 am"], [12, "12 pm"], [18, "6 pm"], [20, "8 pm"]].map(([h, label]) => (
            <Chip key={h} label={label as string} selected={reminderHour === h}
                  onPress={async () => {
                    const ok = await setDailyReminder(h as number);
                    if (ok) setReminderHour(h as number);
                    else Alert.alert("Notifications blocked",
                      "Allow notifications for Ace in Android settings to use reminders.");
                  }} />
          ))}
        </View>
      </Fade>

      <Fade delay={120}>
        <Section title="AI model" />
        <Text style={[type.caption, { marginBottom: 8 }]}>
          Powers your lessons and questions. Applies to new content — switch anytime.
        </Text>
        <Card style={{ padding: 6 }}>
          {models.map((m, i) => (
            <Pressable key={m.id} onPress={() => api.selectModel(m.id)
                         .then((r) => setSelected(r.selected))}
                       style={({ pressed }) => ({
                         flexDirection: "row", alignItems: "center",
                         padding: 12, borderRadius: radius.sm,
                         backgroundColor: pressed ? colors.surfaceRaised : "transparent",
                         borderTopWidth: i === 0 ? 0 : 1, borderTopColor: colors.border,
                       })}>
              <View style={{ width: 18, height: 18, borderRadius: 9, borderWidth: 2, marginRight: 12,
                             borderColor: selected === m.id ? colors.primary : colors.textFaint,
                             alignItems: "center", justifyContent: "center" }}>
                {selected === m.id && (
                  <View style={{ width: 8, height: 8, borderRadius: 4,
                                 backgroundColor: colors.primary }} />
                )}
              </View>
              <Text style={type.bodyStrong}>{m.label}</Text>
            </Pressable>
          ))}
        </Card>

        <View style={{ marginTop: 24 }}>
          <Button label="Sign out" variant="secondary"
                  onPress={() => { signOut(); router.replace("/login"); }} />
        </View>
      </Fade>
    </Screen>
  );
}
