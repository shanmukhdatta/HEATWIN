import { describe, it, expect } from "vitest";
import { indexAt, display } from "./types";
describe("playback", () => {
  it("clamps a simulation time to the available samples", () => {
    expect(indexAt(-3, 10)).toBe(0);
    expect(indexAt(4.7, 10)).toBe(4);
    expect(indexAt(100, 10)).toBe(9);
  });
  it("does not display invalid values as measurements", () => {
    expect(display(NaN)).toBe("—");
    expect(display(54.86)).toBe("54.9");
  });
});
