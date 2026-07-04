# Life Demo Evening Checklist

Use this checklist after work when real household inputs and devices are available. Daytime automation should stay on mock data and desensitized fixtures.

Before staging or recording, review [life-demo-review-package.md](life-demo-review-package.md) to separate upstream-ready code from local helpers, Ubuntu runtime changes, and real-device evidence.

## 0. Review Preflight

Run the review preflight before any staging or recording pass:

```powershell
scripts/preflight-life-demo-review.ps1
```

Expected baseline:

- It prints the current `git status --short` review buckets.
- It prints `Suggested staging groups` from `scripts/plan-life-demo-review-split.ps1`.
- It runs the mock smoke unless `-SkipSmoke` is provided.
- It runs the OpenClaw life skill contract when plugin dependencies are present.
- It runs `git diff --check`.
- It does not commit, push, or create a PR.

If you only need the manual split plan without running smoke tests:

```powershell
scripts/plan-life-demo-review-split.ps1
```

Use the `core-life-demo`, `review-and-recording-support`, `manual-decision-time-compute`, and `local-runtime-only` groups to decide what can be reviewed together and what must stay out of git.

If you need a machine-readable review snapshot for handoff or staging comparison:

```powershell
scripts/export-life-demo-review-manifest.ps1
```

The manifest repeats the staging groups, manual decisions, do-not-commit patterns, and verification commands as JSON.

If you want a Manual staging checklist that is easier to review line by line:

```powershell
scripts/prepare-life-demo-staging-checklist.ps1
```

It prints the same groups in review order and does not run `git add`.

If you want an explanation of the manual decisions before choosing staging options:

```powershell
scripts/explain-life-demo-manual-decisions.ps1
scripts/explain-life-demo-manual-decisions.ps1 -Json
```

The Manual decision explainer summarizes the current `time_compute.py` decision, review support scope, private runtime evidence boundary, 1810/1811 claim split, `MIMO_TTS_API_KEY` state, and `next_commands`. It does not run `git add`.

If you want dry-run Staging command preview output before any manual staging:

```powershell
scripts/preview-life-demo-staging-commands.ps1
scripts/preview-life-demo-staging-commands.ps1 -IncludeReviewSupport
scripts/preview-life-demo-staging-commands.ps1 -IncludeReviewSupport -IncludeManualDecision
```

Default mode prints `git add -- ...` commands only for `core-life-demo`. Add `-IncludeReviewSupport` after reviewing helper scripts/docs, and add `-IncludeManualDecision` only if `time_compute.py` belongs in this package. It does not run `git add`.

If you want a short Review readiness gate before recording or staging:

```powershell
scripts/test-life-demo-review-ready.ps1
```

It checks that `unexpected-review-needed` is empty, reports the known `manual-decision-time-compute` item, and counts the `core-life-demo` plus `review-and-recording-support` groups. Use `-Strict` only after deciding whether `time_compute.py` belongs in the review package.

If you want a private-artifact Secret boundary audit before recording or staging:

```powershell
scripts/test-life-demo-secret-boundary.ps1
```

It checks manifest metadata and known local runtime paths so generated media, SQLite proof DBs, `MIMO_TTS_API_KEY`, private LAN URLs, raw MiMo responses, and real household data stay out of git. Use `-FailOnWarning` only when these warnings should block final staging.

If you want one Life Demo Proof Bundle before recording or reviewer handoff:

```powershell
scripts/export-life-demo-proof-bundle.ps1
scripts/export-life-demo-proof-bundle.ps1 -OutputPath .miloco-smoke\life-demo-proof-bundle.md
```

The bundle includes `readiness_summary`, `secret_boundary_summary`, `recording_order`, `verification_commands`, manual decisions, and do-not-commit patterns. It is read-only and does not run `git add`.

If you want one Final staging gate before any manual `git add`:

```powershell
scripts/test-life-demo-final-staging.ps1
scripts/test-life-demo-final-staging.ps1 -Strict
```

The gate aggregates the manifest, Review readiness gate, Secret boundary audit, and Life Demo Proof Bundle parse. Default mode reports known blockers without failing. `-Strict` should only pass after deciding `time_compute.py` and clearing or confirming runtime SQLite proof DB warnings.

If you want one Recording readiness gate before using real camera/audio:

```powershell
scripts/test-life-demo-recording-ready.ps1
scripts/test-life-demo-recording-ready.ps1 -RequireLiveHelpers -Strict
```

The gate checks review state, `E:\new_job\MilocoDev\run-live-demo.ps1`, `E:\new_job\MilocoDev\pc-speaker-server.ps1`, and `MIMO_TTS_API_KEY` without calling real MiMo, real camera, or `pc_speaker`. Use `-RequireLiveHelpers -Strict` only when these missing prerequisites should block the recording pass.

## 1. Mock Smoke

Run the mock smoke first so there is a known-good baseline before touching real data:

```powershell
scripts/smoke-life-demo.ps1
```

For a shorter console-only baseline:

```powershell
scripts/run-life-demo.ps1
```

If the backend service is running, also verify the official CLI seam:

```powershell
scripts/smoke-life-demo.ps1 -SkipLiveCli:$false
miloco-cli life history --db-path .miloco-smoke/life-demo.db --domain cooking --pretty
miloco-cli life demo --persist --db-path .miloco-smoke/life-demo.db --pretty
miloco-cli life history --db-path .miloco-smoke/life-demo.db --source-id demo_afternoon_interview_dinner --pretty
miloco-cli life notify --domain cooking --urgency medium --requires-ack --message "The water may be boiling; please confirm before adding dumplings." --pretty
```

Expected baseline:

- Output includes `Miloco Life Agent Demo`.
- `scripts/smoke-life-demo.ps1` runs the mock demo plus focused backend, SQLite life repo, and CLI life tests using repo-local temp/cache paths.
- The live CLI smoke first runs an empty history check so the recording can show that the SQLite history starts empty rather than silently failing.
- `miloco-cli life demo --persist --db-path .miloco-smoke/life-demo.db --pretty` returns `code: 0` with outfit, cooking, and persistence summary data.
- `miloco-cli life history --db-path .miloco-smoke/life-demo.db --source-id demo_afternoon_interview_dinner --pretty` returns persisted outfit and cooking recommendation history for the current mock MiMo source id.
- `miloco-cli life notify ...` returns text fallback or a mocked `pc_speaker` result without requiring real audio.
- Output names the mock MiMo source.
- Output includes one outfit recommendation and one cooking recommendation.
- Cooking broadcast uses conservative wording such as `Please confirm`.
- SQLite repo smoke can persist mock wardrobe, pantry, preferences, and recommendation history without real household data.
- No real photos, order screenshots, camera frames, speaker URLs, or API keys are written to git-tracked files.

## 2. Real MiMo Input

Use one real MiMo test only after confirming what can be shared for the hackathon recording.

- Try one wardrobe or fridge photo through real MiMo.
- Save only a redacted structured result for later comparison.
- Confirm low-confidence items are flagged for manual review.
- Do not commit real household images or raw real MiMo responses.

## 3. API Smoke

Use the same payload shape as the fixture against the backend seam:

```http
POST /api/life/demo
```

Check that the response contains:

- extracted wardrobe and pantry items
- preferences
- outfit recommendation
- cooking recommendation
- conservative `broadcast_text`
- low-confidence notes
- optional `persistence` summary when `persist` is true and `db_path` points to a local SQLite file
- recommendation history from `GET /api/life/history?db_path=...&source_id=...`

Then test notification fallback:

```http
POST /api/life/notify
```

Run text fallback first. Only configure `pc_speaker_url` after the text path works.

## 4. Speaker And Device Smoke

Before recording the full camera flow, verify the selected MiMo TTS voice with a short Chinese sentence:

```powershell
scripts/test-life-tts-voice.ps1 -DryRun
$env:MIMO_TTS_BASE_URL="https://api.xiaomimimo.com/v1"
$env:MIMO_TTS_API_KEY="<redacted>"
scripts/test-life-tts-voice.ps1 -Voice Chloe -Model mimo-v2.5-tts -OutputPath .miloco-smoke\tts-Chloe.wav
scripts/test-life-tts-voice.ps1 -Voice Chloe -Model mimo-v2.5-tts -SpeakerUrl http://127.0.0.1:18888/say
```

Expected behavior:

- Dry run prints the request shape and does not record camera clips.
- Real TTS uses `mimo-v2.5-tts` through `/chat/completions`.
- The script reads `MIMO_TTS_API_KEY` from the environment and does not print the key.
- Do not commit generated WAV files, API keys, private speaker URLs, or voice-test outputs.
- If Chloe sounds acceptable, keep it as the recording baseline before comparing other voices.

Validate one channel at a time:

- `pc_speaker_url` mock or local PC speaker HTTP service
- ESP32 speaker endpoint if available
- Xiaomi speaker `play-text` as the preferred real-device output after it is physically available and manually authorized

Expected behavior:

- Delivery failure falls back to text.
- The recommendation flow still succeeds when audio is unavailable.
- Kitchen reminders keep `possible`, `may`, or `please confirm` language.

## 5. Safety And Submission Boundary

- Do not commit, push, or create a PR from the official clone until the user manually reviews the diff.
- Do not include API keys, camera URLs, local speaker URLs with secrets, or real family media in commits.
- Do not claim real MiMo, real camera, PC speaker, ESP32, or Xiaomi speaker validation unless that exact path was tested in this session.
- Do not use automatic stove or appliance control in the demo.
- Do not attach outfit or cooking agents to the realtime perception loop.
- Use `POST /api/life/trigger` or `miloco-cli life trigger` for manual, voice-intent, or schedule-triggered runs.
- The 08:30 outfit reminder should use stored wardrobe data plus weather first; capture a camera clip only after the user explicitly asks for visual inspection.

## 6. Recording Notes

A clean recording can show:

1. Mock MiMo input or redacted real MiMo structured result.
2. `scripts/run-life-demo.ps1` output.
3. Empty `GET /api/life/history` output with the recording hint.
4. `POST /api/life/demo` returning structured recommendations and persistence summary.
5. `POST /api/life/trigger` or `miloco-cli life trigger` producing an outfit reminder without camera input.
6. `GET /api/life/history` showing persisted recommendation history filtered to the recorded `source_id`.
7. `POST /api/life/notify` text fallback or mocked `pc_speaker_url`.
8. Manual note that real camera/audio/device validation is separate from the committed code.
