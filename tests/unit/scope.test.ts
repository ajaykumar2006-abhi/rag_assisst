import { describe, expect, it } from "vitest";

import { resolveSearchScope } from "@/services/scope";

const ALL = ["a", "b", "c"];

describe("resolveSearchScope", () => {
  it("searches everything when nothing is selected", () => {
    expect(resolveSearchScope([], ALL, ALL)).toEqual({ ids: null, single: null });
  });

  it("drops selections that are not ready yet", () => {
    expect(resolveSearchScope(["processing-doc"], ["a", "b"], ["a", "b", "processing-doc"])).toEqual({
      ids: ["a", "b"],
      single: null,
    });
  });

  it("uses the single-document route for exactly one ready document", () => {
    expect(resolveSearchScope(["a"], ALL, ALL)).toEqual({ ids: ["a"], single: "a" });
  });

  it("treats 'every ready document' the same as no filter", () => {
    expect(resolveSearchScope(["a", "b", "c"], ALL, ALL)).toEqual({ ids: null, single: null });
  });

  it("passes an explicit subset through", () => {
    expect(resolveSearchScope(["a", "b"], ALL, ALL)).toEqual({ ids: ["a", "b"], single: null });
  });

  it("reports an empty scope when nothing is ready", () => {
    expect(resolveSearchScope(["a"], [], ALL)).toEqual({ ids: [], single: null });
  });
});
