import DateTimePicker from "@react-native-community/datetimepicker";
import * as DocumentPicker from "expo-document-picker";
import { useFocusEffect, useRouter } from "expo-router";
import React, { useCallback, useRef, useState } from "react";
import { Alert, Platform, Pressable, Text, View } from "react-native";
import { Button, Card, Chip, Fade, Screen, Section, Stat } from "@/components/ui";
import { api, Sources } from "@/lib/api";
import { useApp } from "@/lib/store";
import { colors, type } from "@/lib/theme";

type ExamInfo = {
  id: number; name_raw: string; status: string; exam_date: string | null;
  weekly_hours: number; accelerator_id: number | null;
  counts: { topics: number; chunks: number; questions: number };
};

const HOUR_OPTIONS = [3, 5, 7, 10];

const KIND_LABEL: Record<string, string> = {
  syllabus: "Syllabus", textbook: "Textbook", past_questions: "Past questions",
  guidance: "Study guidance", notes: "Notes", unknown: "Analyzing…",
};

export default function Library() {
  const router = useRouter();
  const { examId } = useApp();
  const [exam, setExam] = useState<ExamInfo | null>(null);
  const [sources, setSources] = useState<Sources | null>(null);
  const [showPicker, setShowPicker] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [busyPack, setBusyPack] = useState(false);
  const [starterBusy, setStarterBusy] = useState(false);
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(() => {
    if (!examId) return;
    api.getExam(examId).then(setExam).catch(() => null);
    api.sources(examId).then(setSources).catch(() => null);
  }, [examId]);

  useFocusEffect(useCallback(() => {
    refresh();
    return () => { if (poll.current) { clearInterval(poll.current); poll.current = null; } };
  }, [refresh]));

  const upload = async () => {
    if (!examId) return;
    const res = await DocumentPicker.getDocumentAsync({
      type: ["application/pdf", "application/epub+zip"], multiple: false,
    });
    if (res.canceled || !res.assets?.[0]) return;
    const a = res.assets[0];
    setUploading(true);
    try {
      await api.uploadDocument(examId, { uri: a.uri, name: a.name, mimeType: a.mimeType });
      if (!poll.current) {
        poll.current = setInterval(async () => {
          try {
            const st = await api.ingestionStatus(examId);
            refresh();
            if (st.documents.every((d) => !["pending", "parsing"].includes(d.parse_status))) {
              if (poll.current) { clearInterval(poll.current); poll.current = null; }
            }
          } catch {
            /* transient network blip — next tick retries */
          }
        }, 2000);
      }
    } finally {
      setUploading(false);
    }
  };

  const removeDoc = (docId: number, filename: string) => {
    Alert.alert("Remove this document?",
      `"${filename}" and everything generated from it will be removed from your environment.`,
      [{ text: "Keep it", style: "cancel" },
       { text: "Remove", style: "destructive",
         onPress: async () => {
           if (!examId) return;
           const r = await api.deleteDocument(examId, docId);
           Alert.alert("Removed",
             `${r.chunks_removed} source passages and ${r.generated_questions_removed} generated questions cleaned up.`);
           refresh();
         } }]);
  };

  const togglePack = async () => {
    if (!examId || !sources?.preloaded || busyPack) return;
    const active = sources.preloaded.active_questions > 0;
    const go = async () => {
      setBusyPack(true);
      try {
        if (active) await api.removePreloaded(examId);
        else await api.restorePreloaded(examId);
        refresh();
      } finally {
        setBusyPack(false);
      }
    };
    if (active) {
      Alert.alert("Remove official practice questions?",
        "The 110 real exam questions leave your drills, diagnostics and mocks. You can restore them here anytime.",
        [{ text: "Keep them", style: "cancel" },
         { text: "Remove", style: "destructive", onPress: go }]);
    } else {
      go();
    }
  };

  const setDate = async (d: Date) => {
    if (!examId) return;
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
      d.getDate()).padStart(2, "0")}`;
    await api.patchExam(examId, { exam_date: iso });
    refresh();
  };

  const setHours = async (h: number) => {
    if (!examId) return;
    await api.patchExam(examId, { weekly_hours: h });
    refresh();
  };

  if (!exam) {
    return (
      <Screen title="Library">
        <Card><Text style={type.body}>Loading your environment…</Text></Card>
      </Screen>
    );
  }

  const pack = sources?.preloaded;
  const packActive = (pack?.active_questions ?? 0) > 0;

  return (
    <Screen title="Library" subtitle="Everything Ace knows about this exam — yours to shape">
      <Fade>
        <Card>
          <Text style={type.caption}>EXAM</Text>
          <Text style={[type.title, { marginTop: 4 }]}>{exam.name_raw}</Text>
          <Pressable onPress={() => setShowPicker(true)} style={{ marginTop: 10 }}>
            <Text style={type.body}>
              📅  Exam day:{" "}
              <Text style={{ color: colors.primary, fontWeight: "700" }}>
                {exam.exam_date ?? "not set"}
              </Text>
              <Text style={type.caption}>   (tap to change)</Text>
            </Text>
          </Pressable>
          {showPicker && (
            <DateTimePicker
              value={exam.exam_date ? new Date(exam.exam_date + "T00:00:00")
                : new Date(Date.now() + 60 * 24 * 3600 * 1000)}
              mode="date"
              display={Platform.OS === "android" ? "calendar" : "spinner"}
              minimumDate={new Date(Date.now() + 24 * 3600 * 1000)}
              onChange={(event, picked) => {
                setShowPicker(false);
                if (event.type !== "dismissed" && picked) setDate(picked);
              }}
            />
          )}
          <Text style={[type.body, { marginTop: 10, marginBottom: 6 }]}>Weekly study hours</Text>
          <View style={{ flexDirection: "row", gap: 8 }}>
            {HOUR_OPTIONS.map((h) => (
              <Chip key={h} label={`${h}h`} selected={exam.weekly_hours === h}
                    onPress={() => setHours(h)} flex />
            ))}
          </View>
        </Card>
      </Fade>

      <Fade delay={60}>
        <Section title="Environment" />
        <View style={{ flexDirection: "row", gap: 8 }}>
          <Stat value={String(exam.counts.topics)} label="topics" />
          <Stat value={String(exam.counts.questions)} label="questions" accent />
          <Stat value={String(exam.counts.chunks)} label="source chunks" />
        </View>
        <View style={{ marginTop: 8 }}>
          <Button label="Browse the syllabus topics →" variant="secondary"
                  onPress={() => router.push("/topics")} />
        </View>
      </Fade>

      {!pack && exam.counts.chunks === 0
        && !sources?.documents.some((d) => d.kind === "starter") && (
        <Fade delay={90}>
          <Section title="Empty environment" />
          <Card tone="primary">
            <Text style={type.bodyStrong}>Let Ace build you a starter pack</Text>
            <Text style={[type.body, { marginTop: 4 }]}>
              A topic map and study notes for {exam.name_raw}, written by Ace from its own
              knowledge — clearly labeled AI-generated, so verify against official materials.
              Lessons, drills and the diagnostic switch on once it's built.
            </Text>
            <View style={{ marginTop: 10 }}>
              <Button label={starterBusy ? "Building (a few minutes)…" : "⚡ Build starter pack"}
                      loading={starterBusy}
                      onPress={async () => {
                        if (!examId) return;
                        setStarterBusy(true);
                        try {
                          await api.buildStarterPack(examId);
                          if (!poll.current) {
                            poll.current = setInterval(async () => {
                              try {
                                const st = await api.ingestionStatus(examId);
                                refresh();
                                if (st.documents.some((d) =>
                                    !["pending", "parsing"].includes(d.parse_status))) {
                                  if (poll.current) {
                                    clearInterval(poll.current);
                                    poll.current = null;
                                  }
                                  setStarterBusy(false);
                                }
                              } catch { /* retry next tick */ }
                            }, 3000);
                          }
                        } catch {
                          setStarterBusy(false);
                        }
                      }} />
            </View>
          </Card>
        </Fade>
      )}

      {pack && (
        <Fade delay={90}>
          <Section title="Preloaded by Ace" />
          <Card tone={packActive ? "primary" : undefined}>
            <Text style={{ color: packActive ? colors.primary : colors.textMuted,
                           fontWeight: "700" }}>
              {packActive ? "Official content pack · active" : "Official content pack · removed"}
            </Text>
            <Text style={[type.bodyStrong, { marginTop: 4 }]}>{pack.name}</Text>
            <Text style={[type.body, { marginTop: 2 }]}>
              {pack.topics} syllabus topics (structure) ·{" "}
              {packActive ? `${pack.active_questions} real practice questions`
                : `${pack.removed_questions} questions removed from rotation`}
            </Text>
            <Text style={[type.caption, { marginTop: 6 }]}>{pack.provenance}</Text>
            <View style={{ marginTop: 10 }}>
              <Button
                label={packActive ? "Remove practice questions" : "Restore practice questions"}
                variant={packActive ? "danger" : "secondary"}
                small loading={busyPack} onPress={togglePack} />
            </View>
          </Card>
        </Fade>
      )}

      <Fade delay={120}>
        <Section title={`Your materials (${sources?.documents.length ?? 0})`} />
        {(sources?.documents.length ?? 0) === 0 && (
          <Card>
            <Text style={type.body}>
              No uploads yet. Add your textbook, notes, or past questions — Ace grounds
              lessons and generated questions in what you upload.
            </Text>
          </Card>
        )}
        {sources?.documents.map((d) => (
          <Card key={d.id} style={{ paddingVertical: 12 }}>
            <View style={{ flexDirection: "row", alignItems: "center" }}>
              <Text style={{ fontSize: 20, marginRight: 10 }}>
                {d.parse_status === "parsed" ? "📄" : d.parse_status === "failed" ? "⚠️" : "⏳"}
              </Text>
              <View style={{ flex: 1 }}>
                <Text style={type.bodyStrong} numberOfLines={1}>{d.filename}</Text>
                <Text style={type.caption}>
                  {KIND_LABEL[d.kind] ?? d.kind}
                  {d.page_count ? ` · ${d.page_count} pages` : ""}
                  {d.chunks ? ` · ${d.chunks} passages` : ""}
                  {d.parse_status !== "parsed" ? ` · ${d.parse_status}` : ""}
                </Text>
              </View>
              <Pressable onPress={() => removeDoc(d.id, d.filename)} hitSlop={10}>
                <Text style={{ color: colors.danger, fontSize: 16 }}>🗑</Text>
              </Pressable>
            </View>
          </Card>
        ))}
        <View style={{ marginTop: 10 }}>
          <Button label={uploading ? "Uploading…" : "＋ Add materials"} onPress={upload}
                  loading={uploading} variant="secondary" />
        </View>
      </Fade>
    </Screen>
  );
}
