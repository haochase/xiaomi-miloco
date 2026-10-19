import { afterEach, describe, expect, it } from "vitest";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { processPrivateRgbaFrame } from "../src/processPrivateFrame";

const roots: string[] = [];
afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe("processPrivateRgbaFrame", () => {
  it("returns only redacted pixels and removes the source file", async () => {
    const root = await mkdtemp(join(tmpdir(), "miloco-privacy-pipeline-"));
    roots.push(root);
    const path = join(root, "synthetic.rgba");
    await writeFile(path, Buffer.from([10, 20, 30, 255, 40, 50, 60, 255]));

    const result = await processPrivateRgbaFrame({
      path, temporaryRoot: root, width: 2, height: 1,
      regions: [{ x: 1, y: 0, width: 1, height: 1 }],
    });

    expect(result.status).toBe("processed");
    expect(result.temporaryFrameCleared).toBe(true);
    expect([...result.redactedPixels!]).toEqual([10, 20, 30, 255, 0, 0, 0, 255]);
    expect(JSON.stringify(result)).not.toContain(path);
    await expect(readFile(path)).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("cleans up the source after invalid region and returns a fixed failure", async () => {
    const root = await mkdtemp(join(tmpdir(), "miloco-privacy-pipeline-"));
    roots.push(root);
    const path = join(root, "synthetic.rgba");
    await writeFile(path, Buffer.from([10, 20, 30, 255]));

    const result = await processPrivateRgbaFrame({
      path, temporaryRoot: root, width: 1, height: 1,
      regions: [{ x: 1, y: 0, width: 1, height: 1 }],
    });

    expect(result).toMatchObject({ status: "failed", errorCode: "privacy_processing_failed", temporaryFrameCleared: true });
    expect(result.redactedPixels).toBeNull();
    await expect(readFile(path)).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("does not read or remove a file outside the controlled root", async () => {
    const root = await mkdtemp(join(tmpdir(), "miloco-privacy-pipeline-"));
    roots.push(root);
    const outside = join(root, "outside.rgba");
    await writeFile(outside, Buffer.from([10, 20, 30, 255]));

    const result = await processPrivateRgbaFrame({
      path: outside, temporaryRoot: join(root, "controlled"), width: 1, height: 1,
      regions: [{ x: 0, y: 0, width: 1, height: 1 }],
    });

    expect(result).toMatchObject({ status: "failed", temporaryFrameCleared: false, redactedPixels: null });
    await expect(readFile(outside)).resolves.toEqual(Buffer.from([10, 20, 30, 255]));
  });

  it("does not claim success when cleanup fails", async () => {
    const root = await mkdtemp(join(tmpdir(), "miloco-privacy-pipeline-"));
    roots.push(root);
    const path = join(root, "missing.rgba");
    const result = await processPrivateRgbaFrame({ path, temporaryRoot: root, width: 1, height: 1, regions: [] });

    expect(result).toMatchObject({ status: "failed", errorCode: "temporary_frame_cleanup_failed", temporaryFrameCleared: false, redactedPixels: null });
  });
});
