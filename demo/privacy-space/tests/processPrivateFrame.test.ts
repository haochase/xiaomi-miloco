import { afterEach, describe, expect, it, vi } from "vitest";
import { mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { processPrivateRgbaFrame } from "../src/processPrivateFrame";

const roots: string[] = [];
const TEMP_ROOT = "E:/new_job/10-AIProjects/MilocoDev/.tmp/voice-vision";
afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe("processPrivateRgbaFrame", () => {
  it("returns only redacted pixels and removes the source file", async () => {
    const root = await mkdtemp(join(TEMP_ROOT, "miloco-privacy-pipeline-"));
    roots.push(root);
    const path = join(root, "synthetic.rgba");
    await writeFile(path, Buffer.from([10, 20, 30, 255, 40, 50, 60, 255]));

    const result = await processPrivateRgbaFrame({
      path, temporaryRoot: root, width: 2, height: 1,
      regions: [{ x: 1, y: 0, width: 1, height: 1 }],
    });

    expect(result.status).toBe("processed");
    expect(result.temporaryFrameCleared).toBe(true);
    expect([...result.getRedactedPixels()!]).toEqual([10, 20, 30, 255, 0, 0, 0, 255]);
    const firstRead = result.getRedactedPixels()!;
    firstRead[0] = 99;
    expect(result.getRedactedPixels()![0]).toBe(10);
    expect(JSON.stringify(result)).not.toContain(path);
    expect(JSON.stringify(result)).not.toContain("redactedPixels");
    expect(JSON.stringify(result)).not.toContain("10");
    expect(Object.keys(result)).not.toContain("redactedPixels");
    await expect(readFile(path)).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("cleans up the source after invalid region and returns a fixed failure", async () => {
    const root = await mkdtemp(join(TEMP_ROOT, "miloco-privacy-pipeline-"));
    roots.push(root);
    const path = join(root, "synthetic.rgba");
    await writeFile(path, Buffer.from([10, 20, 30, 255]));

    const result = await processPrivateRgbaFrame({
      path, temporaryRoot: root, width: 1, height: 1,
      regions: [{ x: 1, y: 0, width: 1, height: 1 }],
    });

    expect(result).toMatchObject({ status: "failed", errorCode: "privacy_processing_failed", temporaryFrameCleared: true });
    expect(result.getRedactedPixels()).toBeNull();
    await expect(readFile(path)).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("does not read or remove a file outside the controlled root", async () => {
    const root = await mkdtemp(join(TEMP_ROOT, "miloco-privacy-pipeline-"));
    roots.push(root);
    const outside = join(root, "outside.rgba");
    await writeFile(outside, Buffer.from([10, 20, 30, 255]));

    const result = await processPrivateRgbaFrame({
      path: outside, temporaryRoot: join(root, "controlled"), width: 1, height: 1,
      regions: [{ x: 0, y: 0, width: 1, height: 1 }],
    });

    expect(result).toMatchObject({ status: "failed", temporaryFrameCleared: false });
    expect(result.getRedactedPixels()).toBeNull();
    await expect(readFile(outside)).resolves.toEqual(Buffer.from([10, 20, 30, 255]));
  });

  it("does not claim success when cleanup fails", async () => {
    const root = await mkdtemp(join(TEMP_ROOT, "miloco-privacy-pipeline-"));
    roots.push(root);
    const path = join(root, "synthetic.rgba");
    await writeFile(path, Buffer.from([10, 20, 30, 255]));
    const result = await processPrivateRgbaFrame({
      path, temporaryRoot: root, width: 1, height: 1, regions: [],
      deleteFrame: async () => { throw new Error("cleanup failed"); },
    });

    expect(result).toMatchObject({ status: "failed", errorCode: "temporary_frame_cleanup_failed", temporaryFrameCleared: false });
    expect(result.getRedactedPixels()).toBeNull();
  });

  it("does not follow a symlink to a file outside the temporary root", async () => {
    const root = await mkdtemp(join(TEMP_ROOT, "miloco-privacy-pipeline-"));
    roots.push(root);
    const outside = join(root, "outside.rgba");
    const controlled = join(root, "controlled");
    await mkdir(controlled);
    await writeFile(outside, Buffer.from([10, 20, 30, 255]));
    const link = join(controlled, "linked.rgba");
    try {
      await symlink(outside, link);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "EPERM") return;
      throw error;
    }

    const result = await processPrivateRgbaFrame({ path: link, temporaryRoot: controlled, width: 1, height: 1, regions: [] });

    expect(result).toMatchObject({ status: "failed", errorCode: "privacy_processing_failed", temporaryFrameCleared: false, redactedPixels: null });
    await expect(readFile(outside)).resolves.toEqual(Buffer.from([10, 20, 30, 255]));
  });

  it("rejects an input larger than the declared frame before reading it", async () => {
    const root = await mkdtemp(join(TEMP_ROOT, "miloco-privacy-pipeline-"));
    roots.push(root);
    const path = join(root, "oversized.rgba");
    await writeFile(path, Buffer.alloc(5_000_000));
    const readFrame = vi.fn(async () => { throw new Error("must not read oversized input"); });

    const statFrame = vi.fn(async () => ({ size: 5_000_000, isSymbolicLink: () => false, isFile: () => true }));
    const result = await processPrivateRgbaFrame({ path, temporaryRoot: root, width: 1, height: 1, regions: [], readFrame, statFrame });

    expect(result).toMatchObject({ status: "failed", errorCode: "privacy_processing_failed", temporaryFrameCleared: true });
    expect(result.getRedactedPixels()).toBeNull();
    expect(readFrame).not.toHaveBeenCalled();
    expect(statFrame).toHaveBeenCalledOnce();
    await expect(readFile(path)).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("rejects symlink metadata before reading a frame", async () => {
    const root = await mkdtemp(join(TEMP_ROOT, "miloco-privacy-pipeline-"));
    roots.push(root);
    const path = join(root, "linked.rgba");
    await writeFile(path, Buffer.from([10, 20, 30, 255]));
    const readFrame = vi.fn(async () => Buffer.from([10, 20, 30, 255]));
    const statFrame = vi.fn(async () => ({ size: 4, isSymbolicLink: () => true, isFile: () => true }));

    const result = await processPrivateRgbaFrame({ path, temporaryRoot: root, width: 1, height: 1, regions: [], statFrame, readFrame });

    expect(result).toMatchObject({ status: "failed", errorCode: "privacy_processing_failed", temporaryFrameCleared: false });
    expect(result.getRedactedPixels()).toBeNull();
    expect(readFrame).not.toHaveBeenCalled();
    await expect(readFile(path)).resolves.toEqual(Buffer.from([10, 20, 30, 255]));
  });
});
