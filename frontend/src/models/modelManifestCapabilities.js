import { useEffect, useState } from "react";
import { api } from "../api/client";

/** @param {Record<string, any> | null | undefined} manifest */
export function initialManifestIssues(manifest) {
  if (Array.isArray(manifest?.configurationIssues)) {
    return manifest.configurationIssues.map(String);
  }
  if (Array.isArray(manifest?.capabilities?.unresolved)) {
    return manifest.capabilities.unresolved.map(String);
  }
  return [];
}

/**
 * Validate an editable manifest with the backend parser used by model imports.
 * @param {Record<string, any> | null} manifest
 */
export function useManifestValidation(manifest) {
  const [validation, setValidation] = useState(() => ({
    manifest,
    issues: initialManifestIssues(manifest),
    validating: Boolean(manifest),
  }));

  useEffect(() => {
    if (!manifest) {
      setValidation({ manifest: null, issues: [], validating: false });
      return undefined;
    }
    const controller = new AbortController();
    setValidation({
      manifest,
      issues: initialManifestIssues(manifest),
      validating: true,
    });
    void api("/api/models/validate-manifest", {
      method: "POST",
      body: JSON.stringify({ manifest }),
      signal: controller.signal,
    })
      .then((result) => {
        if (controller.signal.aborted) return;
        const issues = Array.isArray(result?.issues)
          ? result.issues.map(String)
          : ["The backend returned an invalid manifest-validation response."];
        setValidation({ manifest, issues, validating: false });
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        const message = error instanceof Error ? error.message : String(error);
        setValidation({
          manifest,
          issues: [`Manifest validation is unavailable: ${message}`],
          validating: false,
        });
      });
    return () => controller.abort();
  }, [manifest]);

  if (validation.manifest === manifest) {
    return validation;
  }
  return {
    manifest,
    issues: initialManifestIssues(manifest),
    validating: Boolean(manifest),
  };
}
