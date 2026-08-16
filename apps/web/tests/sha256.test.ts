import { Blob as NodeBlob } from "node:buffer";
import { describe, expect, it } from "vitest";
import { sha256 } from "@/lib/sha256";

describe("sha256", () => {
  it("returns lowercase hexadecimal", async () => {
    const blob = new NodeBlob(["abc"]) as unknown as Blob;
    expect(await sha256(blob)).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  });
});
