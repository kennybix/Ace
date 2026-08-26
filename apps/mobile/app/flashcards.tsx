import { useRouter } from "expo-router";
import React, { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, Text, View } from "react-native";
import { Bar, Button, Card, Fade } from "@/components/ui";
import { api } from "@/lib/api";
import { useApp } from "@/lib/store";
import { colors, s, type } from "@/lib/theme";

type CardT = { front: string; back: string; topic_code: string };

export default function Flashcards() {
  const router = useRouter();
  const { examId } = useApp();
  const [queue, setQueue] = useState<CardT[] | null>(null);
  const [total, setTotal] = useState(0);
  const [seen, setSeen] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rebuilding, setRebuilding] = useState(false);

  const load = (rebuild = false) => {
    if (!examId) return;
    setQueue(null);
    setError(null);
    setSeen(0);
    api.flashcards(examId, rebuild)
      .then((r) => { setQueue(r.cards); setTotal(r.cards.length); })
      .catch((e) => setError((e instanceof Error ? e.message : String(e))
        .replace(/^\d+: /, "")))
      .finally(() => setRebuilding(false));
  };
  useEffect(() => { load(); }, [examId]);

  if (error) {
    return (
      <View style={[s.screen, { justifyContent: "center" }]}>
        <Card>
          <Text style={type.title}>No deck yet</Text>
          <Text style={[type.body, { marginVertical: 8 }]}>{error}</Text>
          <Button label="Back" onPress={() => router.back()} />
        </Card>
      </View>
    );
  }

  if (!queue) {
    return (
      <View style={[s.screen, { justifyContent: "center", alignItems: "center" }]}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={[type.body, { marginTop: 10 }]}>
          {rebuilding ? "Building a fresh deck from your weakest topics…" : "Shuffling cards…"}
        </Text>
      </View>
    );
  }

  if (queue.length === 0) {
    return (
      <View style={[s.screen, { justifyContent: "center" }]}>
        <Fade>
          <Card style={{ alignItems: "center", paddingVertical: 24 }}>
            <Text style={{ fontSize: 44 }}>🃏</Text>
            <Text style={[type.title, { marginTop: 6 }]}>Deck cleared</Text>
            <Text style={type.body}>{total} cards down. Recall is how it sticks.</Text>
          </Card>
          <View style={{ gap: 8, marginTop: 10 }}>
            <Button label="Run it again, fresh deck"
                    onPress={() => { setRebuilding(true); load(true); }} />
            <Button label="Done" variant="secondary" onPress={() => router.back()} />
          </View>
        </Fade>
      </View>
    );
  }

  const card = queue[0];
  const advance = (again: boolean) => {
    setFlipped(false);
    setQueue(again ? [...queue.slice(1), card] : queue.slice(1));
    if (!again) setSeen(seen + 1);
  };

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.bg }}
                contentContainerStyle={{ padding: 20, paddingBottom: 32 }}>
      <View style={{ marginBottom: 12 }}>
        <Text style={[type.caption, { marginBottom: 6 }]}>
          FLASHCARD SPRINT · {seen} OF {total} CLEARED
        </Text>
        <Bar value={total ? seen / total : 0} height={6} />
      </View>

      <Pressable onPress={() => setFlipped(!flipped)}>
        <Card style={{ minHeight: 260, justifyContent: "center", padding: 22 }}>
          <Text style={[type.caption, { marginBottom: 10 }]}>
            {card.topic_code} · {flipped ? "ANSWER" : "TAP TO FLIP"}
          </Text>
          <Text style={flipped ? [type.body, { color: colors.text, fontSize: 16 }]
            : [type.title, { lineHeight: 28 }]}>
            {flipped ? card.back : card.front}
          </Text>
        </Card>
      </Pressable>

      {flipped && (
        <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
          <View style={{ flex: 1 }}>
            <Button label="↻ Again" variant="secondary" onPress={() => advance(true)} />
          </View>
          <View style={{ flex: 1 }}>
            <Button label="Got it ✓" onPress={() => advance(false)} />
          </View>
        </View>
      )}
    </ScrollView>
  );
}
