import type { DemoState } from "./demoSchema";
import { demoState } from "./demoData";
import { projectHostFacts } from "./hostAdapter";

export function selectDemoScenario(name: string | null): DemoState {
  if (name === "room-names") {
    return projectHostFacts({ rooms: [{ id: "living", name: "客厅" }] });
  }
  if (name === "unknown") return projectHostFacts({});
  return demoState;
}
