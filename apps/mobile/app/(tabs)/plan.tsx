import { useFocusEffect } from "expo-router";
import React, { useCallback, useState } from "react";
import { Text, View } from "react-native";
import { Card, Fade, Screen } from "@/components/ui";
import { api, PlanItem } from "@/lib/api";
import { useApp } from "@/lib/store";
import { colors, type } from "@/lib/theme";

const KIND: Record<string, { glyph: string; label: string }> = {
  learn: { glyph: "📘", label: "Study session" },
  review: { glyph: "🔁", label: "Review" },
  mock: { glyph: "⚔️", label: "Mock exam" },
  taper: { glyph: "🎯", label: "Taper revision" },
};

function fmtDay(d: string): string {
  return new Date(d + "T00:00:00").toLocaleDateString(undefined,
    { weekday: "short", month: "short", day: "numeric" });
}

export default function Plan() {
  const { examId } = useApp();
  const [items, setItems] = useState<PlanItem[]>([]);
  const [rationale, setRationale] = useState("");
  const [lifetimeDone, setLifetimeDone] = useState(0);

  useFocusEffect(useCallback(() => {
    if (!examId) return;
    api.getPlan(examId)
      .then((r) => { setItems(r.items); setRationale(r.rationale);
                     setLifetimeDone(r.completed_sessions); })
      .catch(() => setItems([]));
  }, [examId]));

  return (
    <Screen title="The road to exam day"
            subtitle={items.length
              ? `${lifetimeDone} session${lifetimeDone === 1 ? "" : "s"} completed · ${items.length} scheduled`
              : undefined}>
      {!!rationale && (
        <Fade>
          <Card tone="primary">
            <Text style={type.body}>{rationale}</Text>
          </Card>
        </Fade>
      )}
      <Fade delay={80}>
        {items.map((it, idx) => {
          const k = KIND[it.kind] ?? { glyph: "•", label: it.kind };
          const isDone = it.status === "done";
          const isNext = !isDone && items.findIndex((x) => x.status !== "done") === idx;
          return (
            <View key={it.id} style={{ flexDirection: "row", gap: 12 }}>
              {/* timeline spine */}
              <View style={{ alignItems: "center", width: 20 }}>
                <View style={{ width: 2, flex: 1,
                               backgroundColor: idx === 0 ? "transparent" : colors.border }} />
                <View style={{ width: 12, height: 12, borderRadius: 6,
                               backgroundColor: isDone ? colors.success
                                 : isNext ? colors.primary : colors.surfaceRaised,
                               borderWidth: 2,
                               borderColor: isDone ? colors.success
                                 : isNext ? colors.primary : colors.border }} />
                <View style={{ width: 2, flex: 1,
                               backgroundColor: idx === items.length - 1 ? "transparent"
                                 : colors.border }} />
              </View>
              <Card style={{ flex: 1, opacity: isDone ? 0.55 : 1,
                             borderColor: isNext ? colors.primary : colors.border }}>
                <View style={{ flexDirection: "row", alignItems: "center" }}>
                  <Text style={{ fontSize: 18, marginRight: 10 }}>{k.glyph}</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={type.bodyStrong}>
                      {k.label}
                      {it.topic_codes?.length
                        ? `  ·  ${it.topic_codes.slice(0, 4).join(", ")}` : ""}
                    </Text>
                    <Text style={type.caption}>{fmtDay(it.day)} · ~{it.est_minutes} min</Text>
                  </View>
                  {isDone && <Text style={{ color: colors.success, fontSize: 16 }}>✓</Text>}
                  {isNext && (
                    <Text style={{ color: colors.primary, fontSize: 12, fontWeight: "700" }}>
                      NEXT
                    </Text>
                  )}
                </View>
              </Card>
            </View>
          );
        })}
        {items.length === 0 && (
          <Card style={{ alignItems: "center", paddingVertical: 28 }}>
            <Text style={{ fontSize: 34 }}>🗺️</Text>
            <Text style={[type.subtitle, { marginTop: 8 }]}>No plan yet</Text>
            <Text style={[type.body, { textAlign: "center", marginTop: 4 }]}>
              Complete the diagnostic and your route appears here.
            </Text>
          </Card>
        )}
      </Fade>
    </Screen>
  );
}
