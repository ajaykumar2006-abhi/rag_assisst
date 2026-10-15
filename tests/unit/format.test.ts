import { describe, expect, it } from "vitest";

import {
  answerModeLabel,
  formatBytes,
  formatDateTime,
  formatMetric,
  formatMilliseconds,
  formatPercent,
  formatRelative,
  formatUptime,
  parseAnswerSegments,
  pluralize,
  stageStateLabel,
  statusLabel,
  truncate,
} from "@/services/format";

describe("formatBytes", () => {
  it("formats each magnitude with a sensible precision", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1024)).toBe("1.0 KB");
    expect(formatBytes(20 * 1024)).toBe("20 KB");
    expect(formatBytes(1024 * 1024)).toBe("1.0 MB");
  });

  it("degrades gracefully for invalid input", () => {
    expect(formatBytes(Number.NaN)).toBe("0 B");
    expect(formatBytes(-5)).toBe("0 B");
  });
});

describe("formatPercent and formatMetric", () => {
  it("renders percentages with the requested precision", () => {
    expect(formatPercent(0.8123)).toBe("81%");
    expect(formatPercent(0.8123, 1)).toBe("81.2%");
  });

  it("renders a dash rather than NaN", () => {
    expect(formatPercent(Number.NaN)).toBe("—");
    expect(formatMetric(Number.NaN)).toBe("—");
  });

  it("keeps four decimal places for recall-style metrics", () => {
    expect(formatMetric(0.5)).toBe("0.5000");
  });
});

describe("formatMilliseconds", () => {
  it("switches to seconds past one thousand milliseconds", () => {
    expect(formatMilliseconds(240)).toBe("240 ms");
    expect(formatMilliseconds(1500)).toBe("1.50 s");
  });
});

describe("formatUptime", () => {
  it("escalates through seconds, minutes and hours", () => {
    expect(formatUptime(42)).toBe("42s");
    expect(formatUptime(90)).toBe("1m 30s");
    expect(formatUptime(3720)).toBe("1h 2m");
  });
});

describe("formatDateTime and formatRelative", () => {
  it("returns a dash for missing or invalid timestamps", () => {
    expect(formatDateTime(null)).toBe("—");
    expect(formatDateTime("not-a-date")).toBe("—");
    expect(formatRelative(undefined)).toBe("—");
  });

  it("describes recent timestamps relative to a reference instant", () => {
    const now = new Date("2026-02-01T12:00:00Z");
    expect(formatRelative("2026-02-01T11:59:59Z", now)).toBe("just now");
    expect(formatRelative("2026-02-01T11:59:50Z", now)).toBe("10s ago");
    expect(formatRelative("2026-02-01T11:30:00Z", now)).toBe("30m ago");
    expect(formatRelative("2026-02-01T09:00:00Z", now)).toBe("3h ago");
    expect(formatRelative("2026-01-25T12:00:00Z", now)).toBe("7d ago");
  });
});

describe("label helpers", () => {
  it("maps status, stage and answer mode values to readable text", () => {
    expect(statusLabel("ready")).toBe("Ready");
    expect(statusLabel("failed")).toBe("Failed");
    expect(stageStateLabel("running")).toBe("Running");
    expect(answerModeLabel("extractive")).toContain("Extractive");
    expect(answerModeLabel("insufficient")).toBe("Insufficient evidence");
  });
});

describe("parseAnswerSegments", () => {
  it("splits text and citation markers in order", () => {
    const segments = parseAnswerSegments("Alpha [1] beta [2].");
    expect(segments).toEqual([
      { kind: "text", value: "Alpha " },
      { kind: "citation", value: "[1]", index: 1 },
      { kind: "text", value: " beta " },
      { kind: "citation", value: "[2]", index: 2 },
      { kind: "text", value: "." },
    ]);
  });

  it("returns a single text segment when there are no markers", () => {
    expect(parseAnswerSegments("No citations here.")).toEqual([
      { kind: "text", value: "No citations here." },
    ]);
  });

  it("handles an answer that is only a marker", () => {
    expect(parseAnswerSegments("[3]")).toEqual([{ kind: "citation", value: "[3]", index: 3 }]);
  });

  it("preserves multi-digit citation numbers", () => {
    const segments = parseAnswerSegments("See [12].");
    expect(segments[1]).toEqual({ kind: "citation", value: "[12]", index: 12 });
  });

  it("does not treat bracketed words as citations", () => {
    expect(parseAnswerSegments("The [note] here")).toEqual([
      { kind: "text", value: "The [note] here" },
    ]);
  });
});

describe("truncate and pluralize", () => {
  it("adds an ellipsis only when the value is longer than the limit", () => {
    expect(truncate("short", 20)).toBe("short");
    expect(truncate("abcdefghij", 5)).toBe("abcd…");
  });

  it("pluralises with an optional explicit plural", () => {
    expect(pluralize(1, "document")).toBe("document");
    expect(pluralize(2, "document")).toBe("documents");
    expect(pluralize(2, "index", "indexes")).toBe("indexes");
  });
});
