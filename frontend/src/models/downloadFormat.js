/** Shared formatting for model-install `DownloadJob`s, used by both the
 * Models settings panel and the activity drawer's download list. */
import { useToast } from "../components";
import { useServerStore } from "../state/serverStore";

/** @param {number | null | undefined} bytes */
export function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes == null || bytes < 0) return null;
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unit = units[0];
  for (let index = 1; value >= 1024 && index < units.length; index += 1) {
    value /= 1024;
    unit = units[index];
  }
  return `${value >= 10 ? value.toFixed(0) : value.toFixed(1)} ${unit}`;
}

/** @param {number | null | undefined} seconds */
export function formatEta(seconds) {
  if (!Number.isFinite(seconds) || seconds == null || seconds < 0) return null;
  const rounded = Math.ceil(seconds);
  if (rounded < 60) return `${rounded}s remaining`;
  return `${Math.ceil(rounded / 60)}m remaining`;
}

/** "X of Y · Z/s · ETA remaining" - the transfer-progress portion shared by
 * ModelsPanel's `formatTransfer` and BottomDrawer's `downloadSubtitle`.
 * @param {{downloadedBytes?: number | null, totalBytes?: number | null, bytesPerSecond?: number | null, etaSeconds?: number | null}} job
 */
export function formatTransferProgress(job) {
  const downloaded = formatBytes(job.downloadedBytes);
  const total = formatBytes(job.totalBytes);
  const speed = formatBytes(job.bytesPerSecond);
  const eta = formatEta(job.etaSeconds);
  const parts = [];
  if (downloaded && total) parts.push(`${downloaded} of ${total}`);
  else if (downloaded) parts.push(downloaded);
  if (speed) parts.push(`${speed}/s`);
  if (eta) parts.push(eta);
  return parts.join(" · ");
}

/** Cancel an in-progress model install/download with a consistent toast. */
export function useCancelInstall() {
  const toast = useToast();
  const cancelDownload = useServerStore((store) => store.cancelDownload);
  return async function cancelInstall(/** @type {number} */ jobId) {
    try {
      await cancelDownload(jobId);
      toast.push(
        "Cancellation requested. Partial installation is being rolled back.",
        "success",
      );
    } catch (error) {
      toast.push(
        error instanceof Error ? error.message : String(error),
        "error",
      );
    }
  };
}
