import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import React, { useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, Text, View } from "react-native";
import { Markdown, VideoEmbed } from "@/components/content";
import { Bar, Button, Card, Fade, Section } from "@/components/ui";
import { api, TopicDetail } from "@/lib/api";
import { colors, radius, s, type } from "@/lib/theme";

export default function TopicScreen() {
  const router = useRouter();
  const { topicId } = useLocalSearchParams<{ topicId: string }>();
  const tid = Number(topicId);
  const [t, setT] = useState<TopicDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [lessonBusy, setLessonBusy] = useState(false);
  const [videoBusy, setVideoBusy] = useState(false);
  const [videoNote, setVideoNote] = useState<string | null>(null);
  const [drillBusy, setDrillBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = () => {
    setLoadError(null);
    return api.topicDetail(tid)
      .then(setT)
      .catch((e) => setLoadError((e instanceof Error ? e.message : String(e))
        .replace(/^\d+: /, "")));
  };
  useEffect(() => { refresh(); }, [tid]);

  if (loadError && !t) {
    return (
      <View style={[s.screen, { justifyContent: "center" }]}>
        <Card>
          <Text style={type.title}>Couldn't load this topic</Text>
          <Text style={[type.body, { marginVertical: 8 }]}>{loadError}</Text>
          <Button label="Try again" onPress={refresh} />
        </Card>
      </View>
    );
  }

  const writeLesson = async () => {
    setLessonBusy(true);
    setError(null);
    try {
      await api.topicLesson(tid);
      await refresh();
    } catch (e) {
      setError((e instanceof Error ? e.message : String(e)).replace(/^\d+: /, ""));
    } finally {
      setLessonBusy(false);
    }
  };

  const findVideo = async () => {
    setVideoBusy(true);
    setVideoNote(null);
    try {
      const r = await api.topicVideo(tid);
      if (!r.video && r.note) setVideoNote(r.note);
      await refresh();
    } finally {
      setVideoBusy(false);
    }
  };

  const drill = async () => {
    setDrillBusy(true);
    setError(null);
    try {
      const r = await api.topicDrill(tid);
      router.push({ pathname: "/drill/[sessionId]", params: { sessionId: String(r.session_id) } });
    } catch (e) {
      setError((e instanceof Error ? e.message : String(e)).replace(/^\d+: /, ""));
    } finally {
      setDrillBusy(false);
    }
  };

  if (!t) {
    return (
      <View style={[s.screen, { justifyContent: "center", alignItems: "center" }]}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <>
      <Stack.Screen options={{ title: `Topic ${t.code}` }} />
      <ScrollView style={{ flex: 1, backgroundColor: colors.bg }}
                  contentContainerStyle={{ padding: 20, paddingBottom: 40 }}>
        <Fade>
          <Text style={type.title}>{t.title}</Text>
          <View style={{ flexDirection: "row", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
            {t.cognitive_levels.map((c) => (
              <View key={c} style={{ backgroundColor: colors.surfaceRaised,
                                     borderRadius: radius.pill, paddingVertical: 4,
                                     paddingHorizontal: 10 }}>
                <Text style={{ color: colors.textMuted, fontSize: 11.5 }}>{c}</Text>
              </View>
            ))}
            <View style={{ backgroundColor: colors.surfaceRaised, borderRadius: radius.pill,
                           paddingVertical: 4, paddingHorizontal: 10 }}>
              <Text style={{ color: colors.textMuted, fontSize: 11.5 }}>
                {t.question_count} practice Qs
              </Text>
            </View>
          </View>
          {t.mastery !== null && (
            <View style={{ marginTop: 12 }}>
              <Text style={[type.caption, { marginBottom: 4 }]}>
                MASTERY · {Math.round((t.mastery ?? 0) * 100)}% · {t.attempts} attempts
              </Text>
              <Bar value={t.mastery} />
            </View>
          )}
        </Fade>

        <Fade delay={60}>
          <Section title="Lesson" />
          {t.lesson ? (
            <>
              <Card>
                <Markdown body={t.lesson.body} />
              </Card>
              <Button label={lessonBusy ? "Rewriting…" : "↻  Rewrite this lesson (deeper)"}
                      variant="ghost" small loading={lessonBusy}
                      onPress={async () => {
                        setLessonBusy(true);
                        try {
                          await api.topicLesson(tid, true);
                          await refresh();
                        } finally {
                          setLessonBusy(false);
                        }
                      }} />
            </>
          ) : (
            <Card>
              <Text style={type.body}>
                No lesson written yet. Ace writes one from your materials on demand.
              </Text>
              <View style={{ marginTop: 10 }}>
                <Button label={lessonBusy ? "Writing your lesson…" : "✍️  Write my lesson"}
                        onPress={writeLesson} loading={lessonBusy} variant="secondary" />
              </View>
            </Card>
          )}

          <Section title="Video" />
          {t.video ? (
            <Card style={{ padding: 8 }}>
              <VideoEmbed youtubeId={t.video.youtube_id}
                          title={`${t.video.title} · vetted for this topic`} />
            </Card>
          ) : (
            <Card>
              <Text style={type.body}>
                {videoNote ?? "No vetted video yet for this topic."}
              </Text>
              <View style={{ marginTop: 10 }}>
                <Button label={videoBusy ? "Hunting + verifying…" : "🎬  Find me a video"}
                        onPress={findVideo} loading={videoBusy} variant="secondary" />
              </View>
            </Card>
          )}

          <Section title="Practice" />
          <Button label={drillBusy ? "…" : `🎯  Drill this topic`} onPress={drill}
                  loading={drillBusy} />

          {error && (
            <Card tone="danger">
              <Text style={{ color: colors.danger }}>{error}</Text>
            </Card>
          )}
        </Fade>
      </ScrollView>
    </>
  );
}
