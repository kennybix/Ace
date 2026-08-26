# Building the Ace APK & installing on a phone

Same approach as ReadAPage (`ReadAPage/docs/dev-build-and-device.md`): local `expo prebuild`
+ Gradle release build — no Expo account / EAS needed. Toolchain already on this machine:
JDK 17 at `~/jdks/jdk-17.0.19+10`, Android SDK at `~/Android`.

## Build

```bash
cd apps/mobile
# app.json → expo.extra.apiUrl must point at the machine running the API on your Wi-Fi
# (currently http://<your-lan-ip>:8040). Standalone builds can't auto-discover the host.
CI=1 npx expo prebuild -p android --clean
cd android
JAVA_HOME=$HOME/jdks/jdk-17.0.19+10 ANDROID_HOME=$HOME/Android CI=1 \
  ./gradlew app:assembleRelease -x lint -x test
# → app/build/outputs/apk/release/app-release.apk  (copied to repo root as Ace.apk)
```

Notes baked into config (survive `prebuild --clean`):
- `expo-build-properties` sets `usesCleartextTraffic=true` — release builds otherwise refuse
  plain-HTTP LAN APIs — and pins `kotlinVersion: 1.9.25` (SDK 52's expo-modules-core ships a
  Compose Compiler that requires 1.9.25; the template resolves 1.9.24 and compileReleaseKotlin fails).
- Ace is Expo SDK 52 / RN 0.76 → prebuild's default Gradle works with JDK 17 as-is
  (the Gradle-9/IBM_SEMERU pin from ReadAPage's RN 0.85 doc does not apply here).
- `android/` is gitignored and regenerated; don't hand-edit it.

## Install on the phone

USB (developer mode + USB debugging enabled, same as ReadAPage setup):
```bash
~/Android/platform-tools/adb install -r Ace.apk
```
Or just copy `Ace.apk` to the phone (Quick Share / Drive / cable) and tap it —
allow "install unknown apps" when prompted.

## Runtime requirements

- The API runs as a **systemd user service** (`ace-api`, enabled + linger — starts on boot,
  restarts on failure, auto-starts the `ace-db` container). No manual `make dev` needed.
  Manage with `systemctl --user {status,restart} ace-api`.
- **Connectivity (candidate probing):** the app tries, in order:
  1. **Tailscale** `http://<your-tailscale-ip>:8040` (machine `your-machine`) — works from any
     network, incl. cellular, as long as this machine is on and the phone's Tailscale is
     connected (phone `your-phone` is already in the tailnet);
  2. **Wi-Fi LAN** `http://<your-lan-ip>:8040` — same-Wi-Fi fallback if Tailscale is off.
  The login screen shows which one connected. If the LAN IP changes, only that fallback
  needs updating — Tailscale IPs are stable.
- Long-term (Phase 4 beta): deploy the API properly and add its URL as first candidate.
- Sign-in: OTP code is echoed in-app (dev mode) — no email delivery needed yet.
