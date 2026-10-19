import { selectDemoScenario } from "./demoScenario";
import type { DemoState } from "./demoSchema";

export function refreshDemoScenario(name: string | null): DemoState {
  return selectDemoScenario(name);
}
