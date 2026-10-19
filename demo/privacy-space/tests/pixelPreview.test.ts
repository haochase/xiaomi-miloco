import { describe, expect, it } from "vitest";
import { rgbaPixelsToCss } from "../src/pixelPreview";

describe("rgbaPixelsToCss", () => {
  it("maps each RGBA pixel to an exact CSS color", () => {
    const pixels = new Uint8ClampedArray([70, 120, 100, 255, 0, 0, 0, 255]);
    expect(rgbaPixelsToCss(pixels, 2, 1)).toEqual([
      "rgba(70, 120, 100, 1)",
      "rgba(0, 0, 0, 1)",
    ]);
  });

  it("rejects a buffer that does not match the declared dimensions", () => {
    expect(() => rgbaPixelsToCss(new Uint8ClampedArray(4), 2, 1)).toThrow("invalid preview pixels");
  });
});
