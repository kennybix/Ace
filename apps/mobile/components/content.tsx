import React from "react";
import { Text, View } from "react-native";
import WebView from "react-native-webview";
import { colors, radius, type } from "@/lib/theme";

/* ---------- Markdown-lite renderer: headings, bullets, bold — no dependencies ---------- */

function Inline({ text, style }: { text: string; style: object }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  return (
    <Text style={style}>
      {parts.map((p, i) =>
        p.startsWith("**") && p.endsWith("**") ? (
          <Text key={i} style={{ fontWeight: "700", color: colors.text }}>
            {p.slice(2, -2)}
          </Text>
        ) : (
          <Text key={i}>{p}</Text>
        ),
      )}
    </Text>
  );
}

export function Markdown({ body }: { body: string }) {
  const lines = body.replace(/\r/g, "").split("\n");
  const blocks: React.ReactNode[] = [];
  let para: string[] = [];
  const flush = (key: string) => {
    if (para.length) {
      blocks.push(<Inline key={key} text={para.join(" ")}
                          style={[type.body, { color: colors.text, marginBottom: 10 }]} />);
      para = [];
    }
  };
  lines.forEach((raw, i) => {
    const line = raw.trim();
    if (!line) { flush(`p${i}`); return; }
    if (line.startsWith("### ") || line.startsWith("## ")) {
      flush(`p${i}`);
      blocks.push(<Text key={`h${i}`} style={[type.subtitle, { marginTop: 8, marginBottom: 6 }]}>
        {line.replace(/^#+\s*/, "")}</Text>);
    } else if (line.startsWith("# ")) {
      flush(`p${i}`);
      blocks.push(<Text key={`h${i}`} style={[type.title, { marginBottom: 8 }]}>
        {line.slice(2)}</Text>);
    } else if (/^[-*•]\s+/.test(line)) {
      flush(`p${i}`);
      blocks.push(
        <View key={`b${i}`} style={{ flexDirection: "row", marginBottom: 5, paddingLeft: 4 }}>
          <Text style={{ color: colors.primary, marginRight: 8 }}>•</Text>
          <View style={{ flex: 1 }}>
            <Inline text={line.replace(/^[-*•]\s+/, "")}
                    style={[type.body, { color: colors.text }]} />
          </View>
        </View>,
      );
    } else {
      para.push(line);
    }
  });
  flush("tail");
  return <View>{blocks}</View>;
}

/* ---------- In-app YouTube embed (referer-safe wrapper) ---------- */

export function VideoEmbed({ youtubeId, title }: { youtubeId: string; title?: string }) {
  return (
    <View>
      <View style={{ borderRadius: radius.md, overflow: "hidden", aspectRatio: 16 / 9 }}>
        <WebView
          source={{
            baseUrl: "https://ace-app.dev",
            html: `<html><body style="margin:0;background:#000">
              <iframe width="100%" height="100%"
                src="https://www.youtube.com/embed/${youtubeId}?playsinline=1&rel=0"
                frameborder="0" allowfullscreen
                allow="accelerometer; encrypted-media; gyroscope; picture-in-picture">
              </iframe></body></html>`,
          }}
          allowsFullscreenVideo
          allowsInlineMediaPlayback
          style={{ flex: 1, backgroundColor: "#000" }}
        />
      </View>
      {title ? (
        <Text style={[type.caption, { marginTop: 6 }]} numberOfLines={2}>▶ {title}</Text>
      ) : null}
    </View>
  );
}
