import { describe, expect, it } from "vitest";
import { stableWearConfirmationId } from "@/components/outfit/wearConfirmationId";

describe("wear confirmation retry identity", () => {
  it("reuses a generated confirmation id for the same in-flight option", () => {
    const first = stableWearConfirmationId("recommendation-1", "option-2");

    expect(first).toContain("recommendation-1:option-2:");
    expect(stableWearConfirmationId("recommendation-1", "option-2", first)).toBe(
      first,
    );
  });
});
