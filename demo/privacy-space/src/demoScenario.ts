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
    return projectHostFacts(parseHostPrivacyFactsFixture({
      schemaVersion: 1,
      rooms: [{ id: "living", name: "客厅" }],
      anonymousPeopleCount: 0,
      outfit: { scene: "通勤", candidates: ["浅色上衣"], ready: true },
      futureExtension: "ignored",
    }));
  }
  return demoState;
}
