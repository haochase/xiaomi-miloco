import { describe, expect, it } from "vitest";
import { redactRgbaFrame } from "../src/redactFrame";

describe("redactRgbaFrame", () => {
  it("covers a sensitive rectangle and leaves the other pixels unchanged", () => {
    const input = new Uint8ClampedArray([
      10, 20, 30, 255, 40, 50, 60, 255,
      70, 80, 90, 255, 100, 110, 120, 255,
    ]);
    const result = redactRgbaFrame({ width: 2, height: 2, pixels: input }, [{ x: 1, y: 0, width: 1, height: 2 }]);

    expect([...result.pixels]).toEqual([
      10, 20, 30, 255, 0, 0, 0, 255,
      70, 80, 90, 255, 0, 0, 0, 255,
    ]);
    expect([...input]).toEqual([
      10, 20, 30, 255, 40, 50, 60, 255,
      70, 80, 90, 255, 100, 110, 120, 255,
    ]);
    expect(result.redactedPixelCount).toBe(2);
  });

  it("rejects invalid frame and region bounds", () => {
    expect(() => redactRgbaFrame({ width: 2, height: 2, pixels: new Uint8ClampedArray(3) }, [])).toThrow("invalid frame");
    expect(() => redactRgbaFrame({ width: 2, height: 2, pixels: new Uint8ClampedArray(16) }, [{ x: 2, y: 0, width: 1, height: 1 }])).toThrow("invalid region");
  });
});
