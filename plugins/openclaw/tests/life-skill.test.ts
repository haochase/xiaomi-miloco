import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const repoRoot = path.resolve(__dirname, "../../..");

function readRepoFile(...parts: string[]) {
  return readFileSync(path.join(repoRoot, ...parts), "utf8");
}

describe("miloco-life-agent skill contract", () => {
  it("documents the mock MiMo to life recommendation demo path", () => {
    const skill = readRepoFile("plugins", "skills", "miloco-life-agent", "SKILL.md");

    expect(skill).toContain("name: miloco-life-agent");
    expect(skill).toContain("miloco-life-demo");
    expect(skill).toContain("miloco-cli life demo");
    expect(skill).toContain("miloco-cli life trigger");
    expect(skill).toContain("miloco-cli life history");
    expect(skill).toContain("miloco-cli life notify");
    expect(skill).toContain("POST /api/life/demo");
    expect(skill).toContain("POST /api/life/trigger");
    expect(skill).toContain("GET /api/life/history");
    expect(skill).toContain("POST /api/life/notify");
    expect(skill).toContain("scripts/smoke-life-demo.ps1");
    expect(skill).toContain("scripts/run-life-demo.ps1");
    expect(skill).toContain("scripts/test-life-tts-voice.ps1");
    expect(skill).toContain("mock MiMo");
    expect(skill).toContain("Do not attach this skill to the realtime perception loop");
    expect(skill).toContain("must not open the camera unless");
  });

  it("keeps kitchen reminder guidance conservative", () => {
    const skill = readRepoFile("plugins", "skills", "miloco-life-agent", "SKILL.md");

    expect(skill).toContain("possible");
    expect(skill).toContain("please confirm");
    expect(skill).toContain("must not say");
    expect(skill).toContain("already cooked");
    expect(skill).toContain("must turn off");
  });

  it("provides an evening smoke checklist for real-data validation", () => {
    const checklist = readRepoFile("knowledge", "04-testing", "life-demo-evening-checklist.md");

    expect(checklist).toContain("mock smoke");
    expect(checklist).toContain("real MiMo");
    expect(checklist).toContain("pc_speaker_url");
    expect(checklist).toContain("ESP32");
    expect(checklist).toContain("empty history");
    expect(checklist).toContain("scripts/smoke-life-demo.ps1");
    expect(checklist).toContain("scripts/preflight-life-demo-review.ps1");
    expect(checklist).toContain("Do not commit");
    expect(checklist).toContain("scripts/test-life-tts-voice.ps1 -DryRun");
    expect(checklist).toContain("Do not commit generated WAV files");
  });
});
