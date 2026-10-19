import { describe, expect, it } from "vitest";
import { demoState } from "../src/demoData";
import { serializeDemoState } from "../src/demoSchema";

describe("privacy space demo state", () => {
  it("contains only structured, low-sensitivity fields", () => {
    const serialized = serializeDemoState(demoState);

    expect(demoState.rooms.length).toBeGreaterThan(0);
    expect(demoState.devices.some((device) => device.type === "camera")).toBe(true);
    expect(demoState.outfit.candidates.length).toBe(2);
    expect(serialized).not.toMatch(/owner|device_id|token|path|secret|raw|provider/i);
  });

});
