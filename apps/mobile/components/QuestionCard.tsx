import React, { useState } from "react";
import { Pressable, Text, TextInput, View } from "react-native";
import { Button, Card } from "@/components/ui";
import { Question, Reveal } from "@/lib/api";
import { colors, radius, s, type } from "@/lib/theme";

type Props = {
  q: Question;
  onSubmit: (answer: Record<string, unknown>, confidence: string) => Promise<Reveal>;
  onNext: () => void;
  hideConfidence?: boolean;
};

const CONF = [
  { key: "sure", label: "Sure" },
  { key: "think", label: "Think so" },
  { key: "guess", label: "Guessing" },
];

const FMT_LABEL: Record<Question["format"], string> = {
  mcq: "Multiple choice", tf: "True / False", gap: "Fill the gap",
  match: "Match pairs", numeric: "Calculate",
};

export default function QuestionCard({ q, onSubmit, onNext, hideConfidence }: Props) {
  const [mcqIdx, setMcqIdx] = useState<number | null>(null);
  const [tfVal, setTfVal] = useState<boolean | null>(null);
  const [gapText, setGapText] = useState("");
  const [numText, setNumText] = useState("");
  const [pairs, setPairs] = useState<number[][]>([]);
  const [leftSel, setLeftSel] = useState<number | null>(null);
  const [conf, setConf] = useState("think");
  const [reveal, setReveal] = useState<Reveal | null>(null);
  const [busy, setBusy] = useState(false);

  const answer = (): Record<string, unknown> | null => {
    switch (q.format) {
      case "mcq": return mcqIdx === null ? null : { index: mcqIdx };
      case "tf": return tfVal === null ? null : { value: tfVal };
      case "gap": return gapText.trim() ? { text: gapText.trim() } : null;
      case "numeric": return numText.trim() ? { value: Number(numText) } : null;
      case "match": return pairs.length === (q.payload.left?.length ?? 0) ? { pairs } : null;
    }
  };

  const submit = async () => {
    const a = answer();
    if (!a || busy) return;
    setBusy(true);
    try { setReveal(await onSubmit(a, conf)); } finally { setBusy(false); }
  };

  const stem = q.payload.stem ?? q.payload.statement ?? q.payload.text_with_gap
    ?? "Match the pairs";

  return (
    <Card style={{ padding: 18 }}>
      <View style={{ flexDirection: "row", gap: 8, marginBottom: 10 }}>
        <Tag text={FMT_LABEL[q.format]} />
        <Tag text={q.cognitive_level} />
      </View>
      <Text style={[type.title, { marginBottom: 14, lineHeight: 27 }]}>{stem}</Text>

      {q.format === "mcq" && (q.payload.options ?? []).map((opt, i) => (
        <Option key={i} letter={"ABCD"[i]} label={opt} selected={mcqIdx === i}
                good={reveal ? i === reveal.correct_index : undefined}
                onPress={() => !reveal && setMcqIdx(i)} />
      ))}

      {q.format === "tf" && [true, false].map((v) => (
        <Option key={String(v)} letter={v ? "T" : "F"} label={v ? "True" : "False"}
                selected={tfVal === v}
                good={reveal ? v === reveal.answer : undefined}
                onPress={() => !reveal && setTfVal(v)} />
      ))}

      {q.format === "gap" && (
        <TextInput style={s.input} placeholder="Type the missing term…"
                   placeholderTextColor={colors.textFaint}
                   value={gapText} onChangeText={setGapText} editable={!reveal} />
      )}

      {q.format === "numeric" && (
        <TextInput style={s.input}
                   placeholder={`Your answer${q.payload.unit ? ` (${q.payload.unit})` : ""}`}
                   placeholderTextColor={colors.textFaint} keyboardType="numeric"
                   value={numText} onChangeText={setNumText} editable={!reveal} />
      )}

      {q.format === "match" && (
        <View style={{ flexDirection: "row", gap: 8 }}>
          <View style={{ flex: 1 }}>
            {(q.payload.left ?? []).map((l, i) => (
              <Option key={i} letter={String(i + 1)} label={l}
                      selected={leftSel === i || pairs.some((p) => p[0] === i)}
                      onPress={() => !reveal && setLeftSel(i)} />
            ))}
          </View>
          <View style={{ flex: 1 }}>
            {(q.payload.right ?? []).map((r, j) => (
              <Option key={j} letter={"abcd"[j] ?? "•"} label={r}
                      selected={pairs.some((p) => p[1] === j)}
                      onPress={() => {
                        if (reveal || leftSel === null) return;
                        setPairs([...pairs.filter((p) => p[0] !== leftSel), [leftSel, j]]);
                        setLeftSel(null);
                      }} />
            ))}
          </View>
        </View>
      )}

      {!reveal && (
        <>
          {!hideConfidence && (
            <View style={{ flexDirection: "row", gap: 6, marginVertical: 14,
                           backgroundColor: colors.surfaceRaised, borderRadius: radius.pill,
                           padding: 4 }}>
              {CONF.map((c) => (
                <Pressable key={c.key} onPress={() => setConf(c.key)}
                           style={{ flex: 1, paddingVertical: 8, borderRadius: radius.pill,
                                    alignItems: "center",
                                    backgroundColor: conf === c.key ? colors.surface
                                      : "transparent" }}>
                  <Text style={{ color: conf === c.key ? colors.text : colors.textFaint,
                                 fontSize: 12.5, fontWeight: "600" }}>{c.label}</Text>
                </Pressable>
              ))}
            </View>
          )}
          <View style={{ marginTop: hideConfidence ? 14 : 0 }}>
            <Button label="Submit" onPress={submit} loading={busy} disabled={answer() === null} />
          </View>
        </>
      )}

      {reveal && (
        <View style={{ marginTop: 14, backgroundColor: reveal.correct ? colors.successBg
                         : colors.dangerBg,
                       borderRadius: radius.md, padding: 14, borderWidth: 1,
                       borderColor: reveal.correct ? "rgba(95,195,119,0.35)"
                         : "rgba(240,113,113,0.35)" }}>
          <Text style={{ color: reveal.correct ? colors.success : colors.danger,
                         fontWeight: "800", fontSize: 16 }}>
            {reveal.correct ? "✓  Correct" : "✕  Not quite"}
          </Text>

          {/* why your pick was wrong — the most important sentence on the screen */}
          {!reveal.correct && q.format === "mcq" && mcqIdx !== null
            && reveal.option_notes?.["ABCD"[mcqIdx]] && (
            <Text style={[type.body, { marginTop: 6, color: colors.text }]}>
              <Text style={{ fontWeight: "700", color: colors.danger }}>
                Your answer ({"ABCD"[mcqIdx]}): </Text>
              {reveal.option_notes["ABCD"[mcqIdx]]}
            </Text>
          )}

          {!!reveal.explanation && (
            <Text style={[type.body, { marginTop: 6, color: colors.text }]}>
              {!reveal.correct && reveal.correct_index !== undefined && (
                <Text style={{ fontWeight: "700", color: colors.success }}>
                  Why {"ABCD"[reveal.correct_index]} is right: </Text>
              )}
              {reveal.explanation}
            </Text>
          )}

          {/* every option, one line each */}
          {reveal.option_notes && (
            <View style={{ marginTop: 10, borderTopWidth: 1,
                           borderTopColor: "rgba(255,255,255,0.08)", paddingTop: 8 }}>
              {Object.entries(reveal.option_notes).map(([L, note]) => (
                <Text key={L} style={[type.caption, { marginBottom: 4, lineHeight: 17 }]}>
                  <Text style={{ fontWeight: "800",
                                 color: L === "ABCD"[reveal.correct_index ?? -1]
                                   ? colors.success : colors.textMuted }}>{L}.</Text> {note}
                </Text>
              ))}
            </View>
          )}

          {reveal.citations?.length > 0 && (
            <Text style={[type.caption, { marginTop: 8 }]}>
              📎 Grounded in your materials
            </Text>
          )}
          <View style={{ marginTop: 12 }}>
            <Button label="Next" onPress={onNext} />
          </View>
        </View>
      )}
    </Card>
  );
}

function Tag({ text }: { text: string }) {
  return (
    <View style={{ backgroundColor: colors.surfaceRaised, borderRadius: radius.pill,
                   paddingVertical: 4, paddingHorizontal: 10 }}>
      <Text style={{ color: colors.textMuted, fontSize: 11.5, fontWeight: "600" }}>{text}</Text>
    </View>
  );
}

function Option({ letter, label, selected, good, onPress }: {
  letter: string; label: string; selected: boolean; good?: boolean; onPress: () => void;
}) {
  const showCorrect = good === true;
  const showWrong = good === false && selected;
  const border = showCorrect ? colors.success : showWrong ? colors.danger
    : selected ? colors.primary : colors.border;
  const badgeBg = showCorrect ? colors.success : showWrong ? colors.danger
    : selected ? colors.primary : colors.surfaceRaised;
  const badgeFg = showCorrect || showWrong || selected ? colors.primaryFg : colors.textMuted;
  return (
    <Pressable onPress={onPress}
               style={({ pressed }) => ({
                 flexDirection: "row", alignItems: "center",
                 backgroundColor: showCorrect ? colors.successBg
                   : showWrong ? colors.dangerBg : colors.surfaceRaised,
                 borderWidth: 1.5, borderColor: border, borderRadius: radius.md,
                 padding: 12, marginVertical: 4,
                 transform: [{ scale: pressed ? 0.985 : 1 }],
               })}>
      <View style={{ width: 26, height: 26, borderRadius: 13, backgroundColor: badgeBg,
                     alignItems: "center", justifyContent: "center", marginRight: 10 }}>
        <Text style={{ color: badgeFg, fontWeight: "800", fontSize: 12.5 }}>{letter}</Text>
      </View>
      <Text style={{ color: colors.text, fontSize: 14.5, lineHeight: 20, flex: 1 }}>{label}</Text>
    </Pressable>
  );
}
