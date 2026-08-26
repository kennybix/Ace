import DateTimePicker from "@react-native-community/datetimepicker";
import * as DocumentPicker from "expo-document-picker";
import { useRouter } from "expo-router";
import React, { useEffect, useRef, useState } from "react";
import { Alert, Platform, Pressable, Text, View } from "react-native";
import { TextInput } from "react-native";
import { Button, Card, Chip, Fade, Screen, Section } from "@/components/ui";
import { api } from "@/lib/api";
import { useApp } from "@/lib/store";
import { colors, s, type } from "@/lib/theme";

type Step = "details" | "upload" | "confirm";
const STEPS: Step[] = ["details", "upload", "confirm"];
const HOUR_OPTIONS = [3, 5, 7, 10];

function fmtDate(d: Date): string {
  return d.toLocaleDateString(undefined, { weekday: "short", year: "numeric",
                                           month: "long", day: "numeric" });
}

function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate()).padStart(2, "0")}`;
}

function StepDots({ step }: { step: Step }) {
  return (
    <View style={{ flexDirection: "row", gap: 6, marginBottom: 20 }}>
      {STEPS.map((x, i) => (
        <View key={x}
              style={{ height: 4, flex: 1, borderRadius: 2,
                       backgroundColor: STEPS.indexOf(step) >= i ? colors.primary
                         : colors.surfaceRaised }} />
      ))}
    </View>
  );
}

export default function Onboarding() {
  const router = useRouter();
  const { examId, setExamId } = useApp();
  const [step, setStep] = useState<Step>("details");
  const [name, setName] = useState("");
  const [date, setDate] = useState<Date | null>(null);
  const [showPicker, setShowPicker] = useState(false);
  const [hours, setHours] = useState(5);
  const [busy, setBusy] = useState(false);
  const [accelerator, setAccelerator] = useState<string | null>(null);
  const [docs, setDocs] = useState<{ filename: string; kind: string; parse_status: string }[]>([]);
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (poll.current) clearInterval(poll.current); }, []);

  const create = async () => {
    if (!name.trim() || !date || busy) return;
    setBusy(true);
    try {
      const r = await api.createExam(name.trim(), isoDate(date), hours);
      setExamId(r.exam_id);
      setAccelerator(r.accelerator);
      setStep("upload");
    } catch (e) {
      Alert.alert("Couldn't create exam", e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const upload = async () => {
    if (!examId) return;
    const res = await DocumentPicker.getDocumentAsync({
      type: ["application/pdf", "application/epub+zip"], multiple: false,
    });
    if (res.canceled || !res.assets?.[0]) return;
    const a = res.assets[0];
    await api.uploadDocument(examId, { uri: a.uri, name: a.name, mimeType: a.mimeType });
    if (!poll.current) {
      poll.current = setInterval(async () => {
        try {
          const st = await api.ingestionStatus(examId);
          setDocs(st.documents);
        } catch {
          /* transient network blip — next tick retries */
        }
      }, 1500);
    }
  };

  const confirm = async () => {
    if (!examId) return;
    await api.confirmSetup(examId);
    router.replace("/diagnostic");
  };

  return (
    <Screen title={step === "details" ? "Which exam?"
                   : step === "upload" ? "Your materials" : "Ready to baseline"}
            subtitle={step === "details"
              ? "Any exam. Ace figures the rest out from your materials."
              : step === "upload"
                ? "PDFs or EPUBs you own — textbook, syllabus, past questions, notes."
                : "A short diagnostic sets your starting plan. Don't study for it."}
            right={step === "details" && router.canGoBack() ? (
              <Pressable onPress={() => router.back()}>
                <Text style={{ color: colors.textMuted, fontSize: 14, padding: 6 }}>Cancel</Text>
              </Pressable>
            ) : undefined}>
      <StepDots step={step} />

      {step === "details" && (
        <Fade>
          <Section title="Exam name" style={{ marginTop: 0 }} />
          <TextInput style={s.input} placeholder="e.g. CIRE (Canadian Investment Regulatory Exam)"
                     placeholderTextColor={colors.textFaint} value={name} onChangeText={setName} />

          <Section title="Exam date" />
          <Pressable style={s.input} onPress={() => setShowPicker(true)}>
            <Text style={{ color: date ? colors.text : colors.textFaint, fontSize: 16 }}>
              {date ? `📅  ${fmtDate(date)}` : "📅  Pick your exam date"}
            </Text>
          </Pressable>
          {showPicker && (
            <DateTimePicker
              value={date ?? new Date(Date.now() + 60 * 24 * 3600 * 1000)}
              mode="date"
              display={Platform.OS === "android" ? "calendar" : "spinner"}
              minimumDate={new Date(Date.now() + 24 * 3600 * 1000)}
              onChange={(event, picked) => {
                setShowPicker(false);
                if (event.type !== "dismissed" && picked) setDate(picked);
              }}
            />
          )}

          <Section title="Study hours per week" />
          <View style={{ flexDirection: "row", gap: 8, marginBottom: 24 }}>
            {HOUR_OPTIONS.map((h) => (
              <Chip key={h} label={`${h}h`} selected={hours === h} onPress={() => setHours(h)}
                    flex />
            ))}
          </View>

          <Button label="Continue" onPress={create} loading={busy}
                  disabled={!name.trim() || !date} />
        </Fade>
      )}

      {step === "upload" && (
        <Fade>
          {accelerator && (
            <Card tone="primary">
              <Text style={{ color: colors.primary, fontWeight: "700", marginBottom: 4 }}>
                Known exam ✓
              </Text>
              <Text style={type.bodyStrong}>{accelerator}</Text>
              <Text style={type.body}>Syllabus + real practice questions already loaded.</Text>
            </Card>
          )}
          <View style={{ marginTop: 8, gap: 8 }}>
            <Button label="Upload a document" variant="secondary" onPress={upload} />
          </View>
          {docs.map((d) => (
            <Card key={d.filename}>
              <Text style={type.bodyStrong} numberOfLines={1}>{d.filename}</Text>
              <Text style={type.caption}>
                {d.kind === "unknown" ? "analyzing" : d.kind} · {d.parse_status}
              </Text>
            </Card>
          ))}
          <View style={{ marginTop: 16 }}>
            <Button label={accelerator ? "Continue" : "Done uploading"}
                    onPress={() => setStep("confirm")} />
          </View>
        </Fade>
      )}

      {step === "confirm" && (
        <Fade>
          <Card>
            <Text style={type.subtitle}>What happens next</Text>
            <Text style={[type.body, { marginTop: 6 }]}>
              ~20 questions matched to your exam's format and weighting. Your answers set the
              baseline that your day-by-day plan is built from — backwards from exam day.
            </Text>
          </Card>
          <View style={{ marginTop: 12, gap: 8 }}>
            <Button label="Start diagnostic" onPress={confirm} />
            <Button label="Later — take me to the app" variant="ghost"
                    onPress={async () => {
                      if (examId) await api.confirmSetup(examId);
                      router.replace("/(tabs)");
                    }} />
          </View>
        </Fade>
      )}
    </Screen>
  );
}
