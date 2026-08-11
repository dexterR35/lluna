import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/api/client", () => ({ api: vi.fn() }));

import { api } from "../src/api/client";
import {
  initialManifestIssues,
  useManifestValidation,
} from "../src/models/modelManifestCapabilities";

describe("editable model manifest validation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("uses backend issues instead of evaluating a second client-side ruleset", async () => {
    vi.mocked(api).mockResolvedValue({
      valid: false,
      issues: ["guidanceScale"],
    });
    const manifest = {
      task: "text-to-image",
      capabilities: {
        guidance: true,
        unresolved: ["steps"],
      },
      configurationIssues: ["variant.kind"],
    };

    expect(initialManifestIssues(manifest)).toEqual(["variant.kind"]);
    const { result } = renderHook(() => useManifestValidation(manifest));

    await waitFor(() => expect(result.current.validating).toBe(false));

    expect(result.current.issues).toEqual(["guidanceScale"]);
    expect(api).toHaveBeenCalledWith(
      "/api/models/validate-manifest",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ manifest }),
        signal: expect.any(AbortSignal),
      }),
    );
  });
});
