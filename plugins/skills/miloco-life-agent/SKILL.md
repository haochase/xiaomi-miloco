---
name: miloco-life-agent
description: Use when a user asks Miloco to turn clothing, pantry, meal, or family-preference context into an outfit or cooking recommendation. Routes the hackathon demo path through mock MiMo extraction, life recommendations, and conservative notify fallback.
metadata:
  author: miloco
  version: "0.1"
  date: "2026-06-25"
  openclaw:
    requires:
      bins: ["miloco-life-demo", "miloco-cli"]
---

# miloco-life-agent

Use this skill for the "Yi Shi Zhi Jia" life-agent demo: outfit advice, pantry/meal planning, and kitchen reminder wording. The current hackathon slice is a demo-first path. It must keep Xiaomi MiMo visible as the multimodal interpretation layer while keeping Miloco responsible for household memory, recommendation, and notify fallback.

## When To Use

- The user asks what to wear for an occasion using known wardrobe items, weather, style preference, or family member context.
- The user asks what to cook using pantry/fridge/order context, meal size, time budget, or taste restrictions.
- The flow starts from a mock MiMo payload, a desensitized image/text fixture, or a future real MiMo extraction result.
- The user wants to demonstrate the life-agent loop through CLI, backend API, or text/HTTP notification fallback.
- The user intent or schedule explicitly triggers one recommendation run. Do not attach this skill to the realtime perception loop.

Do not use this skill for automatic stove, gas, oven, or appliance control. The demo can recommend and remind, but it must not control cooking devices.

## Demo Entry Points

Run the local mock smoke suite:

```powershell
scripts/smoke-life-demo.ps1
```

Run only the backend console mock demo:

```powershell
scripts/run-life-demo.ps1
```

Probe a MiMo TTS voice before recording the real camera flow:

```powershell
scripts/test-life-tts-voice.ps1 -DryRun
scripts/test-life-tts-voice.ps1 -Voice Chloe -Model mimo-v2.5-tts -OutputPath .miloco-smoke\tts-Chloe.wav
```

Run the Miloco CLI demo path when the backend service is available:

```powershell
miloco-cli life history --db-path .miloco-smoke/life-demo.db --domain cooking --pretty
miloco-cli life trigger --trigger-source schedule --domain outfit --occasion "08:30 outfit reminder" --weather "cool rainy morning" --db-path .miloco-smoke/life-demo.db --pretty
miloco-cli life demo --persist --db-path .miloco-smoke/life-demo.db --pretty
miloco-cli life history --db-path .miloco-smoke/life-demo.db --pretty
miloco-cli life demo --pretty
miloco-cli life notify --domain cooking --urgency medium --requires-ack --message "The water may be boiling; please confirm before adding dumplings." --pretty
```

The script uses the desensitized fixture and the backend console script:

```powershell
miloco-life-demo --fixture backend/miloco/tests/fixtures/life_mimo_mock.json
```

Backend API seams:

```http
POST /api/life/demo
POST /api/life/trigger
GET /api/life/history
POST /api/life/notify
```

`POST /api/life/demo` accepts a mock MiMo style payload and returns structured wardrobe items, pantry items, preferences, outfit recommendation, cooking recommendation, conservative broadcast text, and low-confidence notes.

`POST /api/life/trigger` runs exactly one recommendation from an explicit `manual`, `voice_intent`, or `schedule` trigger. It should use persisted wardrobe or pantry inventory first. It must not open the camera unless the request already carries `clip_base64` or `mimo_payload`.

`GET /api/life/history` reads persisted recommendation history from the explicit demo SQLite path. For recording, run an empty history check first, then run `life demo --persist`, then query history again to show the closed loop.

`POST /api/life/notify` sends the broadcast message through the life notify adapter. During the hackathon demo, prefer text fallback or a mocked `pc_speaker_url`; do not require a real speaker, ESP32, or Xiaomi speaker during daytime automation.

## Required Flow

1. Start from an explicit manual, voice-intent, or schedule trigger.
2. For routine reminders, use persisted wardrobe/pantry/preferences first and avoid camera capture.
3. Start from mock MiMo or a real MiMo extraction result only when the request already includes visual input.
4. Normalize wardrobe, pantry, and preference data through the life schema.
5. Generate outfit and cooking recommendations with clear rationale and risk notes.
6. For cooking reminders, keep the message conservative and require human confirmation.
7. Deliver through text fallback or `pc_speaker_url` mock unless the user is doing after-hours real-device validation.

The demo path should remain:

```text
mock MiMo input -> life extractor -> wardrobe/pantry/preferences -> recommendation -> SQLite history -> notify/text output
schedule/voice/manual trigger -> SQLite inventory -> recommendation -> history -> notify/text output
```

## Kitchen Safety Language

Kitchen reminders must say "possible", "may", or "please confirm" when describing camera/model observations or cooking state.

Good examples:

- "The water may be boiling; please confirm before adding dumplings."
- "The timer is at 6 minutes; please check the dumplings before serving."
- "The stove area may need attention; please confirm the heat source is safe."

The agent must not say:

- "already cooked"
- "must turn off"
- "confirmed safe"
- "ready to eat"

If the user asks for a definitive cooking-safety judgment, answer with a conservative check request and route only a reminder, not a command.

## Data Boundaries

- Daytime automation uses mock or desensitized fixtures only.
- These agents are on-demand. Do not wire them into `PerceptionRunner` or any continuous camera listener.
- The 08:30 outfit reminder should use weather plus stored wardrobe data first; ask before capturing a new camera clip.
- Only capture a short clip when the user explicitly asks to inspect visible clothes, fridge contents, pantry items, or kitchen context.
- Real family photos, real order screenshots, real MiMo keys, real cameras, real speakers, ESP32, and Xiaomi speakers are after-hours manual validation inputs.
- Do not commit real household images, real order data, API keys, speaker URLs with secrets, or camera screenshots.
- Do not scrape Xiaohongshu, Weibo, Douyin, or similar platforms automatically. User-provided text or screenshots can be structured by the agent.

## Verification

For code-level smoke verification, use the backend life tests and the demo script:

```powershell
cd backend/miloco
$env:UV_CACHE_DIR="E:\new_job\MilocoDev\xiaomi-miloco\.uv-cache"
uv run pytest tests/test_life_schema.py tests/test_life_extractor.py tests/test_life_recommender.py tests/test_life_demo_cli.py tests/test_life_demo_script.py tests/test_life_notify.py tests/test_life_router.py -q
```

```powershell
scripts/run-life-demo.ps1
```

For plugin packaging, the OpenClaw plugin copies `plugins/skills/` during its build pre-step.
