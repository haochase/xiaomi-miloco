import type { DemoState } from "./demoSchema";
import { demoState } from "./demoData";
import { projectHostFacts } from "./hostAdapter";
import { parseHostPrivacyFactsFixture } from "./hostFactsFixture";

export function selectDemoScenario(name: string | null): DemoState {
  if (name === "room-names") {
    return projectHostFacts({ rooms: [{ id: "living", name: "客厅" }] });
  }
  if (name === "unknown") return projectHostFacts({});
  if (name === "fixture") {
    const fixture = parseHostPrivacyFactsFixture({
      schemaVersion: 1,
      metadata: { observedAt: "2026-10-19T10:00:00Z", expiresAt: "2026-10-19T10:10:00Z", source: "host" },
      rooms: [{ id: "living", name: "客厅" }],
      anonymousPeopleCount: 0,
      outfit: { scene: "通勤", candidates: ["浅色上衣"], ready: true },
      futureExtension: "ignored",
    });
    return projectHostFacts(fixture, new Date("2026-10-19T10:05:00Z"));
  }
  return demoState;
}
