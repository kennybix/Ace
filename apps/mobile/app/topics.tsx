import { useRouter } from "expo-router";
import React, { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, Text, View } from "react-native";
import { Bar, Card } from "@/components/ui";
import { api, TopicNode } from "@/lib/api";
import { useApp } from "@/lib/store";
import { colors, radius, s, type } from "@/lib/theme";

export default function Topics() {
  const router = useRouter();
  const { examId } = useApp();
  const [topics, setTopics] = useState<TopicNode[]>([]);
  const [open, setOpen] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);

  const [loadError, setLoadError] = useState<string | null>(null);
  const load = () => {
    if (!examId) return;
    setLoading(true);
    setLoadError(null);
    api.topicTree(examId)
      .then((r) => setTopics(r.topics))
      .catch((e) => setLoadError((e instanceof Error ? e.message : String(e))
        .replace(/^\d+: /, "")))
      .finally(() => setLoading(false));
  };
  useEffect(load, [examId]);

  if (loading) {
    return (
      <View style={[s.screen, { justifyContent: "center", alignItems: "center" }]}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  if (loadError) {
    return (
      <View style={[s.screen, { justifyContent: "center" }]}>
        <Card>
          <Text style={type.title}>Couldn't load the syllabus</Text>
          <Text style={[type.body, { marginVertical: 8 }]}>{loadError}</Text>
          <Pressable onPress={load} style={{ alignSelf: "flex-start" }}>
            <Text style={{ color: colors.primary, fontWeight: "700" }}>Try again</Text>
          </Pressable>
        </Card>
      </View>
    );
  }

  const numeric = (code: string) => code.split(".").map((x) => parseInt(x, 10) || 0);
  const byCode = (a: TopicNode, b: TopicNode) => {
    const [pa, pb] = [numeric(a.code), numeric(b.code)];
    return (pa[0] - pb[0]) || ((pa[1] ?? 0) - (pb[1] ?? 0));
  };
  const parents = topics.filter((t) => t.parent_id === null).sort(byCode);
  const childrenOf = (id: number) =>
    topics.filter((t) => t.parent_id === id).sort(byCode);
  const toggle = (id: number) => {
    const next = new Set(open);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setOpen(next);
  };

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.bg }}
                contentContainerStyle={{ padding: 20, paddingBottom: 32 }}>
      <Text style={[type.body, { marginBottom: 12 }]}>
        {parents.length} elements · {topics.length - parents.length} learning outcomes.
        Weights mirror the real exam.
      </Text>
      {parents.map((p) => {
        const kids = childrenOf(p.id);
        const isOpen = open.has(p.id);
        return (
          <Card key={p.id} style={{ padding: 0, overflow: "hidden" }}>
            <Pressable onPress={() => toggle(p.id)}
                       style={({ pressed }) => ({
                         padding: 14,
                         backgroundColor: pressed ? colors.surfaceRaised : "transparent",
                       })}>
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <View style={{ flex: 1 }}>
                  <Text style={type.bodyStrong}>{p.code}. {p.title}</Text>
                  <Text style={type.caption}>
                    ~{Math.round(p.weight)} exam questions · {kids.length} outcomes
                    {p.question_count > 0 ? ` · ${p.question_count} practice Qs` : ""}
                  </Text>
                </View>
                <Text style={{ color: colors.textFaint, fontSize: 16 }}>
                  {isOpen ? "▾" : "▸"}
                </Text>
              </View>
              {p.mastery !== null && (
                <View style={{ marginTop: 8 }}>
                  <Bar value={p.mastery} height={5} />
                </View>
              )}
            </Pressable>
            {isOpen && kids.map((k) => (
              <Pressable key={k.id}
                    onPress={() => router.push({ pathname: "/topic/[topicId]",
                                                 params: { topicId: String(k.id) } })}
                    style={({ pressed }) => ({
                      paddingVertical: 10, paddingHorizontal: 14, borderTopWidth: 1,
                      borderTopColor: colors.border,
                      backgroundColor: pressed ? colors.surfaceRaised
                        : "rgba(255,255,255,0.02)" })}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  <Text style={{ color: colors.textFaint, fontSize: 12.5, width: 34 }}>
                    {k.code}
                  </Text>
                  <View style={{ flex: 1 }}>
                    <Text style={[type.body, { color: colors.text, fontSize: 14 }]}
                          numberOfLines={2}>
                      {k.title}
                    </Text>
                    <View style={{ flexDirection: "row", gap: 6, marginTop: 3,
                                   alignItems: "center" }}>
                      {k.cognitive_levels.map((c) => (
                        <View key={c}
                              style={{ backgroundColor: colors.surfaceRaised,
                                       borderRadius: radius.pill, paddingVertical: 2,
                                       paddingHorizontal: 8 }}>
                          <Text style={{ color: colors.textMuted, fontSize: 10.5 }}>{c}</Text>
                        </View>
                      ))}
                      {k.question_count > 0 && (
                        <Text style={type.caption}>{k.question_count} Qs</Text>
                      )}
                      {k.attempts > 0 && k.mastery !== null && (
                        <Text style={[type.caption,
                                      { color: k.mastery >= 0.7 ? colors.success
                                          : k.mastery >= 0.45 ? colors.primary
                                          : colors.danger }]}>
                          {Math.round(k.mastery * 100)}% mastery
                        </Text>
                      )}
                    </View>
                  </View>
                  <Text style={{ color: colors.textFaint, fontSize: 15 }}>›</Text>
                </View>
              </Pressable>
            ))}
          </Card>
        );
      })}
    </ScrollView>
  );
}
