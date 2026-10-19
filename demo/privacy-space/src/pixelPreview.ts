export function rgbaPixelsToCss(
  pixels: Uint8ClampedArray,
  width: number,
  height: number,
): string[] {
  if (
    !Number.isInteger(width) || !Number.isInteger(height) ||
    width <= 0 || height <= 0 || pixels.length !== width * height * 4
  ) throw new Error("invalid preview pixels");

  const colors: string[] = [];
  for (let index = 0; index < pixels.length; index += 4) {
    colors.push(`rgba(${pixels[index]}, ${pixels[index + 1]}, ${pixels[index + 2]}, ${pixels[index + 3] / 255})`);
  }
  return colors;
}
