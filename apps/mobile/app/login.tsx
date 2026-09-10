import { useRouter } from "expo-router";
import React, { useCallback, useEffect, useState } from "react";
import { Image, Pressable, Text, TextInput, View } from "react-native";
import { Button, Card, ConnPill, Fade, Screen } from "@/components/ui";
import { api, getBase, getServerOverride, healthCheck } from "@/lib/api";
import { saveServerOverride, useApp } from "@/lib/store";
import { colors, s, type } from "@/lib/theme";

type Conn = "checking" | "ok" | "down";

export default function Login() {
  const router = useRouter();
  const { signIn } = useApp();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [devCode, setDevCode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conn, setConn] = useState<Conn>("checking");
  const [editServer, setEditServer] = useState(false);
  const [serverInput, setServerInput] = useState(getServerOverride() ?? "");

  const checkServer = useCallback(async () => {
    setConn("checking");
    setConn((await healthCheck()) ? "ok" : "down");
  }, []);

  useEffect(() => { checkServer(); }, [checkServer]);

  const request = async () => {
    setError(null);
    setBusy(true);
    try {
      const r = await api.requestOtp(email.trim());
      setSent(true);
      if (r.dev_code) setDevCode(r.dev_code);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      checkServer();
    } finally {
      setBusy(false);
    }
  };

  const verify = async () => {
    setError(null);
    setBusy(true);
    try {
      const r = await api.verifyOtp(email.trim(), code.trim());
      signIn(r.token, r.user.email);
      router.replace("/");
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg.startsWith("401") ? "Invalid or expired code — try again." : msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen scroll={false}>
      <View style={{ flex: 1, justifyContent: "center" }}>
        <Fade>
          <View style={{ alignItems: "center", marginBottom: 28 }}>
            <Image source={require("../assets/adaptive-icon.png")}
                   style={{ width: 120, height: 120, marginBottom: 4 }} />
            <Text style={[type.display, { fontSize: 34 }]}>Ace</Text>
            <Text style={[type.body, { textAlign: "center", marginTop: 6 }]}>
              Upload your materials. Set your date.{"\n"}Ace runs your prep.
            </Text>
          </View>
        </Fade>

        <Fade delay={120}>
          <View style={{ alignItems: "center", marginBottom: 6 }}>
            <ConnPill state={conn} detail={getBase().replace("http://", "")}
                      onRetry={checkServer} />
            <Pressable onPress={() => setEditServer(!editServer)}>
              <Text style={{ color: colors.textFaint, fontSize: 12, padding: 8 }}>
                {editServer ? "hide" : "change server address"}
              </Text>
            </Pressable>
          </View>

          {editServer && (
            <View style={{ marginBottom: 10 }}>
              <TextInput style={s.input}
                         placeholder="e.g. quantoptimus.taile8b1de.ts.net or 100.x.y.z"
                         placeholderTextColor={colors.textFaint}
                         autoCapitalize="none" autoCorrect={false}
                         value={serverInput} onChangeText={setServerInput} />
              <Text style={[{ color: colors.textFaint, fontSize: 11.5, marginBottom: 8 }]}>
                On a shared Tailscale machine? Open your Tailscale app → Machines → copy
                the address it shows *you* — it can differ from the owner's.
              </Text>
              <Button label="Save & test" variant="secondary" small
                      onPress={async () => {
                        await saveServerOverride(serverInput || null);
                        setEditServer(false);
                        checkServer();
                      }} />
            </View>
          )}

          {!sent ? (
            <>
              <TextInput style={s.input} placeholder="you@email.com"
                         placeholderTextColor={colors.textFaint}
                         autoCapitalize="none" keyboardType="email-address"
                         value={email} onChangeText={setEmail} editable={!busy} />
              <View style={{ marginTop: 10 }}>
                <Button label="Continue with email" onPress={request}
                        disabled={!email.includes("@")} loading={busy} />
              </View>
            </>
          ) : (
            <>
              {devCode && (
                <Card tone="primary" style={{ alignItems: "center" }}>
                  <Text style={type.caption}>Your sign-in code</Text>
                  <Text style={[type.stat, { color: colors.primary, letterSpacing: 6 }]}>
                    {devCode}
                  </Text>
                </Card>
              )}
              <TextInput style={[s.input, { textAlign: "center", letterSpacing: 8,
                                            fontSize: 20 }]}
                         placeholder="••••••" placeholderTextColor={colors.textFaint}
                         keyboardType="number-pad" maxLength={6}
                         value={code} onChangeText={setCode} editable={!busy} />
              <View style={{ marginTop: 10, gap: 8 }}>
                <Button label="Verify" onPress={verify}
                        disabled={code.trim().length < 6} loading={busy} />
                <Button label="Use a different email" variant="ghost"
                        onPress={() => { setSent(false); setDevCode(null); setCode(""); }} />
              </View>
            </>
          )}

          {error && (
            <Card tone="danger">
              <Text style={{ color: colors.danger, fontSize: 14 }}>{error}</Text>
            </Card>
          )}
        </Fade>
      </View>
    </Screen>
  );
}
