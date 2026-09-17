# VoiceGuard Android companion

This Android Studio project is the mobile companion for the VoiceGuard SIH2614 web/backend prototype.

## What it does
- Detects active calls through Android Telecom `InCallService` when Android allows the app to be registered/eligible for that role.
- Starts a foreground microphone monitor while a call is active.
- Streams 16-bit PCM audio over secure `wss://` to the VoiceGuard backend's `/ws/live` endpoint.
- Shows detection messages in the persistent notification.
- Includes a manual microphone test.

## Important Android platform limitation
A normal third-party Android app cannot universally capture the remote party's private cellular/WhatsApp/other-app call audio. `InCallService` provides call state/control surfaces, but it does not grant unrestricted raw call-audio access. Android/OEM policies can also restrict microphone capture during calls. A production product that requires guaranteed two-sided cellular call audio needs a supported OEM/privileged call-recording integration, a carrier/VoIP architecture, or an audio path under the application's control.

Therefore this is a **complete SIH prototype architecture**, not a claim that ordinary Android APIs can bypass OS privacy controls.

## Build
Open `android/VoiceGuardAndroid` in Android Studio, let Gradle sync, then Build > Build APK(s).

The backend URL should be the WebSocket endpoint, e.g. `https://your-service.onrender.com/ws/live`; the app converts HTTPS to WSS automatically.

For Android 13+, grant microphone and notification permissions. For call-state integration, Android may require the app to be selected/eligible as the appropriate phone/call service depending on OS version and OEM.
