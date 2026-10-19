export type RgbaFrame = {
  width: number;
  height: number;
  pixels: Uint8ClampedArray;
};

export type RedactionRegion = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export function redactRgbaFrame(
  frame: RgbaFrame,
  regions: RedactionRegion[],
): { pixels: Uint8ClampedArray; redactedPixelCount: number } {
  if (
    !Number.isInteger(frame.width) || !Number.isInteger(frame.height) ||
    frame.width <= 0 || frame.height <= 0 ||
    frame.pixels.length !== frame.width * frame.height * 4
  ) throw new Error("invalid frame");

  const output = new Uint8ClampedArray(frame.pixels);
  const covered = new Set<number>();
  for (const region of regions) {
    if (
      ![region.x, region.y, region.width, region.height].every(Number.isInteger) ||
      region.x < 0 || region.y < 0 || region.width <= 0 || region.height <= 0 ||
      region.x + region.width > frame.width || region.y + region.height > frame.height
    ) throw new Error("invalid region");

    for (let y = region.y; y < region.y + region.height; y += 1) {
      for (let x = region.x; x < region.x + region.width; x += 1) {
        const pixelIndex = y * frame.width + x;
        covered.add(pixelIndex);
        output.set([0, 0, 0, 255], pixelIndex * 4);
      }
    }
  }
  return { pixels: output, redactedPixelCount: covered.size };
}
