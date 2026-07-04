# Life Demo Review Package

This note separates the current "Yi Shi Zhi Jia" hackathon demo work into reviewable buckets. Use it before any commit, push, PR, or recording pass.

## Review Goal

The current branch contains a large uncommitted life-demo slice. The reviewer should first decide what belongs in an upstream code review and what must stay as local demo evidence or runtime setup.

Do not commit, push, or open a PR until the user manually reviews these buckets.

## Upstream-ready code

These files are candidates for the official clone if the user accepts the demo direction:

- `backend/miloco/src/miloco/life/`: life schema, mock MiMo extraction, recommendation, SQLite history, notify adapter, live MiMo normalization, router, and quick E2E entry.
- `backend/miloco/tests/test_life_*.py` and `backend/miloco/tests/fixtures/life_mimo_mock.json`: desensitized contract and smoke tests.
- `backend/miloco/pyproject.toml`: `miloco-life-demo` and `miloco-life-quick-e2e` console scripts.
- `backend/miloco/src/miloco/main.py`: life router registration.
- `cli/src/miloco_cli/commands/life.py` and `cli/src/miloco_cli/main.py`: formal CLI seam for demo, notify, and history.
- `scripts/run-life-demo.ps1`, `scripts/smoke-life-demo.ps1`, and `scripts/test-life-tts-voice.ps1`: repo-local mock smoke and secret-safe TTS probe.
- `knowledge/04-testing/life-demo-evening-checklist.md` and `plugins/skills/miloco-life-agent/SKILL.md`: recording and agent instructions.
- `plugins/openclaw/tests/life-skill.test.ts`: OpenClaw-facing skill contract.

Before staging these files, run the review preflight:

```powershell
scripts/preflight-life-demo-review.ps1
```

It runs the current status buckets, the suggested review split plan, `scripts/smoke-life-demo.ps1`, the OpenClaw `life-skill.test.ts` contract when dependencies are present, and `git diff --check`. It does not commit, push, or open a PR.

To generate only the current review snapshot from `git status --short`, run:

```powershell
scripts/review-life-demo-status.ps1
```

Use the output to compare the live worktree against the buckets below before staging anything.

To plan a manual staging split without changing the worktree, run:

```powershell
scripts/plan-life-demo-review-split.ps1
```

It prints `Suggested staging groups` for `core-life-demo`, `review-and-recording-support`, `manual-decision-time-compute`, and `local-runtime-only`. The split plan is advisory only; it does not run `git add`.

To export the same review state as a machine-readable manifest, run:

```powershell
scripts/export-life-demo-review-manifest.ps1
```

The JSON includes `core-life-demo`, `review-and-recording-support`, `manual-decision-time-compute`, `local-runtime-only`, `unexpected-review-needed`, `manual_decisions`, and `verification_commands`. Use it when comparing staged files against the current worktree or when preparing a reviewer handoff note.

To print a Manual staging checklist without changing the worktree, run:

```powershell
scripts/prepare-life-demo-staging-checklist.ps1
```

It converts the manifest into a review order: clear `unexpected-review-needed`, decide `manual-decision-time-compute`, review `core-life-demo`, then review `review-and-recording-support`. No git add is executed by this helper.

To explain the manual decisions and print the next safe commands without changing the worktree, run:

```powershell
scripts/explain-life-demo-manual-decisions.ps1
scripts/explain-life-demo-manual-decisions.ps1 -Json
```

The Manual decision explainer turns the current manifest into choices for `time_compute.py`, review support scripts, private runtime evidence, and 1810/1811 recording claims. Its JSON output includes `next_commands` for the next safe dry-run checks. No git add is executed by this helper.

To print a Staging command preview without changing the worktree, run:

```powershell
scripts/preview-life-demo-staging-commands.ps1
scripts/preview-life-demo-staging-commands.ps1 -IncludeReviewSupport
scripts/preview-life-demo-staging-commands.ps1 -IncludeReviewSupport -IncludeManualDecision
```

Default mode prints dry-run `git add -- ...` commands for `core-life-demo` only. Use `-IncludeReviewSupport` after reviewing the helper scripts/docs, and use `-IncludeManualDecision` only if the user decides `time_compute.py` belongs in this package. No git add is executed by this helper.

To run the Review readiness gate without changing the worktree, run:

```powershell
scripts/test-life-demo-review-ready.ps1
```

It summarizes `unexpected-review-needed`, `manual-decision-time-compute`, `core-life-demo`, and `review-and-recording-support` from the manifest. Default mode reports the known `time_compute.py` manual decision without failing; use `-Strict` before final staging if manual-decision items should block the gate.

To run the Secret boundary audit without changing the worktree, run:

```powershell
scripts/test-life-demo-secret-boundary.ps1
```

It checks the manifest and known runtime artifact paths for private boundary risks: `MIMO_TTS_API_KEY`, private LAN URLs, real household data, raw MiMo responses, generated media, and SQLite proof DBs must stay out of git. Default mode reports warnings without failing; use `-FailOnWarning` before final staging if private-artifact warnings should block the gate.

To export a Life Demo Proof Bundle for reviewer handoff or recording prep, run:

```powershell
scripts/export-life-demo-proof-bundle.ps1
```

It combines the manifest groups, `readiness_summary`, `secret_boundary_summary`, `recording_order`, `verification_commands`, manual decisions, and do-not-commit patterns into one read-only Markdown snapshot. Use `-Json` for machine-readable output or `-OutputPath .miloco-smoke\life-demo-proof-bundle.md` for a local-only file.

To run the Final staging gate before any manual `git add`, run:

```powershell
scripts/test-life-demo-final-staging.ps1
scripts/test-life-demo-final-staging.ps1 -Strict
```

It aggregates the manifest, Review readiness gate, Secret boundary audit, and Life Demo Proof Bundle parse. Default mode reports known blockers without failing; `-Strict` fails while `manual-decision-time-compute` or runtime SQLite proof DB warnings remain unresolved.

To run the Recording readiness gate before a real after-hours recording pass, run:

```powershell
scripts/test-life-demo-recording-ready.ps1
scripts/test-life-demo-recording-ready.ps1 -RequireLiveHelpers -Strict
```

It checks review state plus local helper availability for `E:\new_job\MilocoDev\run-live-demo.ps1`, `E:\new_job\MilocoDev\pc-speaker-server.ps1`, and `MIMO_TTS_API_KEY` without calling real camera, real MiMo, or `pc_speaker`. Default mode reports warnings; `-RequireLiveHelpers -Strict` fails until recording prerequisites are present.

## Local helper scripts

These files are useful for the user's local demo loop but should not be folded into the official upstream clone without a separate decision:

- `E:\new_job\MilocoDev\run-live-demo.ps1`: local orchestration for one explicit camera clip -> existing 1811 life endpoint -> optional speaker. It does not auto-start 1811 unless `-StartSidecarIfDown` is passed.
- `E:\new_job\MilocoDev\pc-speaker-server.ps1`: local Windows speaker HTTP bridge.

Keep private LAN IPs, local speaker URLs, and generated audio out of commits.

## Ubuntu runtime changes

These changes are runtime evidence, not source changes:

- Official Miloco service `1810` stayed healthy and was not replaced.
- Life demo sidecar `1811` was used for development validation, but it must stay an explicit manual runtime choice because it can start a second full-stack Miloco process.
- Active MiMo omni profile was switched on Ubuntu to a working `mimo-v2-omni` endpoint.
- A config backup exists on Ubuntu at `/home/codechase/.openclaw/miloco/config.json.backup-life-20260626021630`.
- Temporary camera clips and SQLite proof files lived under `/tmp`, not git.

Record these in `E:\new_job\MilocoDev\MILOCO_HACKATHON_DEMO_PROGRESS.md`, but do not claim they are reproducible upstream behavior unless the setup is documented and re-run.

## Real-device evidence

Evidence already collected or expected for recording:

- Real camera clip capture through the healthy `1810` Miloco service.
- Real MiMo visual probe from the camera clip into the life sidecar.
- `1811 /api/life/live-demo` returning a normalized outfit recommendation and history record.
- Xiaomi speaker `play-text` delivery through the Miloco MiOT control path, or text/PC speaker fallback when explicitly selected.
- MiMo TTS through `mimo-v2.5-tts` on `/chat/completions` with `Chloe` as the current baseline voice.

Do not commit real household images, raw MiMo responses, generated WAV files, API keys, private speaker URLs, or camera clips.

## Recording Order

Use this order for a clean demo recording:

1. Run `scripts/smoke-life-demo.ps1` to show the mock baseline and quick two-feature E2E pass.
2. Run `scripts/test-life-tts-voice.ps1 -DryRun` to show the secret-safe TTS request shape.
3. For the on-demand no-camera path, run `miloco-cli life trigger --trigger-source schedule --domain outfit --weather "<weather>" --db-path <db> --pretty` against stored wardrobe data.
4. For an explicit visual check only, verify 1811 is already running or intentionally pass `-StartSidecarIfDown`, then run `E:\new_job\MilocoDev\run-live-demo.ps1 -Speak` after pointing the camera at wardrobe or pantry items. The default speaker target is the Xiaomi speaker.
5. Show the `1811` live-demo response summary, including `mimo_source`, recommendation title, low-confidence notes, and history count.
6. For cooking scenes, verify the spoken text says `may`, `possible`, or `please confirm`.
7. Update `MILOCO_HACKATHON_DEMO_PROGRESS.md` with exact commands and whether the run used mock data, real MiMo, real camera, or real audio.

## Do Not Commit

Do not commit these without explicit user approval:

- Generated media: `*.wav`, `*.mp4`, camera clips, screenshots, and local recording exports.
- SQLite proof databases: `.db`, `.sqlite`, `.sqlite3`.
- API keys, Xiaomi account state, local config backups, real MiMo raw payloads, and private LAN URLs with secrets.
- Repo-local temp or cache directories such as `.pytest-tmp/`, `.pytest-tmp-live/`, `.miloco-smoke/`, `.ruff_cache/`, and `.uv-cache/`.
- Unrelated CLI changes such as `cli/src/miloco_cli/commands/time_compute.py` unless the user intentionally includes them in the review package.

## Reviewer Checklist

- Confirm the demo direction is acceptable for the hackathon story.
- Decide whether `cli/src/miloco_cli/commands/time_compute.py` belongs in this package or should be split out.
- Compare the suggested split from `scripts/plan-life-demo-review-split.ps1` with the actual review scope before staging.
- Export the machine-readable manifest with `scripts/export-life-demo-review-manifest.ps1` if the reviewer wants a JSON snapshot.
- Print the Manual staging checklist with `scripts/prepare-life-demo-staging-checklist.ps1` before any manual `git add`.
- Run the Manual decision explainer with `scripts/explain-life-demo-manual-decisions.ps1` to map blockers to review choices and `next_commands`.
- Print the Staging command preview with `scripts/preview-life-demo-staging-commands.ps1`; include review support or `time_compute.py` only after explicit manual review.
- Run the Review readiness gate with `scripts/test-life-demo-review-ready.ps1`; use `-Strict` once `time_compute.py` has been decided.
- Run the Secret boundary audit with `scripts/test-life-demo-secret-boundary.ps1`; use `-FailOnWarning` if any private artifact warning should block final staging.
- Export the Life Demo Proof Bundle with `scripts/export-life-demo-proof-bundle.ps1` before recording or reviewer handoff.
- Run the Final staging gate with `scripts/test-life-demo-final-staging.ps1`; use `-Strict` immediately before any manual staging attempt.
- Run the Recording readiness gate with `scripts/test-life-demo-recording-ready.ps1`; use `-RequireLiveHelpers -Strict` before a real after-hours recording pass.
- Run the review preflight before staging: `scripts/preflight-life-demo-review.ps1`.
- Re-run the mock path before staging: `scripts/smoke-life-demo.ps1`.
- Re-run focused backend and CLI tests if any source changes were made after the last smoke.
- Review all kitchen wording for conservative phrasing before any recording.
- Keep `1810` official service and `1811` sidecar claims separate.
