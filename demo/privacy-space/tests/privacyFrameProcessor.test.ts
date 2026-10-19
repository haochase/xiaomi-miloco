import { afterEach, describe, expect, it, vi } from "vitest";
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PrivacyFrameProcessor } from "../src/privacyFrameProcessor";

const tempRoots: string[] = [];

async function controlledRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "miloco-privacy-demo-"));
  tempRoots.push(root);
  return root;
}

afterEach(async () => {
  await Promise.all(tempRoots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe("PrivacyFrameProcessor", () => {
  it("returns a low-sensitivity summary and deletes the raw frame", async () => {
    const root = await controlledRoot();
    const controlled = join(root, "controlled");
    await mkdir(controlled);
    const input = join(controlled, "raw-frame.bin");
    await writeFile(input, "synthetic-frame");

    const result = await new PrivacyFrameProcessor({}, controlled).process(input);

    expect(result).toEqual({
      status: "processed",
      errorCode: null,
      temporaryFrameCleared: true,
      frameCount: 1,
      summary: "合成画面已完成本地隐私摘要处理",
    });
    await expect(readFile(input)).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("deletes the raw frame when processing fails", async () => {
    const root = await controlledRoot();
    const controlled = join(root, "controlled");
    await mkdir(controlled);
    const input = join(controlled, "raw-frame.bin");
    await writeFile(input, "synthetic-frame");

    const result = await new PrivacyFrameProcessor({ fail: true }, controlled).process(input);

    expect(result).toMatchObject({
      status: "failed",
      errorCode: "privacy_processing_failed",
      temporaryFrameCleared: true,
      frameCount: 1,
    });
    await expect(readFile(input)).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("does not expose paths, identifiers, tokens, or raw provider text", async () => {
    const root = await controlledRoot();
    const controlled = join(root, "controlled");
    await mkdir(controlled);
    const input = join(controlled, "raw-frame.bin");
    await writeFile(input, "synthetic-frame");

    const result = await new PrivacyFrameProcessor({}, controlled).process(input);
    const serialized = JSON.stringify(result);

    expect(serialized).not.toContain(root);
    expect(serialized).not.toMatch(/owner|device|token|provider|raw|secret/i);
    expect(await readdir(controlled)).toEqual([]);
  });

  it("rejects a frame outside the controlled temporary root", async () => {
    const root = await mkdtemp(join(tmpdir(), "miloco-privacy-demo-"));
    tempRoots.push(root);
    const outside = join(root, "outside-frame.bin");
    await writeFile(outside, "synthetic-frame");

    const controlled = join(root, "controlled");
    await mkdir(controlled);
    const result = await new PrivacyFrameProcessor({}, controlled).process(outside);

    expect(result).toMatchObject({ status: "failed", errorCode: "privacy_processing_failed", temporaryFrameCleared: false });
    await expect(readFile(outside)).resolves.toEqual(Buffer.from("synthetic-frame"));
  });

  it("reports cleanup failure instead of claiming the frame was cleared", async () => {
    const root = await mkdtemp(join(tmpdir(), "miloco-privacy-demo-"));
    tempRoots.push(root);
    const input = join(root, "raw-frame.bin");
    await writeFile(input, "synthetic-frame");
    const processor = new PrivacyFrameProcessor({ deleteFrame: vi.fn().mockRejectedValueOnce(new Error("cleanup failed")) }, root);

    const result = await processor.process(input);

    expect(result).toMatchObject({ status: "failed", errorCode: "temporary_frame_cleanup_failed", temporaryFrameCleared: false });
  });
});
