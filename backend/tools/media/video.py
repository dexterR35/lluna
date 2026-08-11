import queue
import subprocess
import threading

import numpy as np

from backend.diagnostics.errors import OutputWriteError

from .ffmpeg import FFmpegCLI


class FramePrefetcher:
    """
    Prefetch/decode video frames on a background thread so I/O overlaps with model inference.
    Interface-compatible with cv2.VideoCapture (read/release).
    """

    def __init__(self, video_cap, buffer_size=10):
        self.cap = video_cap
        self._buffer = queue.Queue(maxsize=buffer_size)
        self._stopped = False
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self):
        while not self._stopped:
            ret, frame = self.cap.read()
            self._buffer.put((ret, frame))
            if not ret:
                break

    def read(self):
        """Read the next frame; same interface as cv2.VideoCapture.read()."""
        return self._buffer.get()

    def get(self, propId):
        return self.cap.get(propId)

    def stop(self):
        """Stop prefetching without releasing the underlying video_cap."""
        self._stopped = True
        try:
            while not self._buffer.empty():
                self._buffer.get_nowait()
        except queue.Empty:
            pass
        self._thread.join(timeout=5)

    def release(self):
        self.stop()
        self.cap.release()


class FFmpegVideoWriter:
    """
    Write frames through an FFmpeg pipe using libx264 encoding.
    Interface-compatible with cv2.VideoWriter (write/release).
    """

    def __init__(self, output_path, fps, size):
        if not output_path:
            raise ValueError("FFmpeg output path cannot be empty")
        w, h = size
        cmd = [
            FFmpegCLI.instance().ffmpeg_path,
            '-y',
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{w}x{h}',
            '-pix_fmt', 'bgr24',
            '-r', str(fps),
            '-i', '-',
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            '-crf', '18',
            '-preset', 'fast',
            '-loglevel', 'error',
            output_path
        ]
        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self._released = False

    def _failure(self):
        detail = ""
        if self._process.stderr is not None:
            try:
                detail = self._process.stderr.read().decode(
                    "utf-8", errors="replace"
                ).strip()
            except (OSError, ValueError):
                detail = ""
        suffix = detail.splitlines()[-1] if detail else "encoder process stopped"
        return OutputWriteError(f"FFmpeg could not write the video: {suffix}")

    def write(self, frame):
        """Write one frame (numpy BGR array)."""
        if self._released or self._process.poll() is not None:
            raise self._failure()
        if frame.dtype != np.uint8:
            frame = np.clip(frame, 0, 255).astype(np.uint8)
        try:
            self._process.stdin.write(frame.tobytes())
        except (BrokenPipeError, OSError, ValueError) as exc:
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.terminate()
                self._process.wait(timeout=5)
            raise self._failure() from exc

    def release(self):
        """Close the pipe and wait for encoding to finish."""
        if self._released:
            return
        self._released = True
        try:
            self._process.stdin.close()
        except (BrokenPipeError, OSError, ValueError):
            pass
        try:
            self._process.wait(timeout=600)
        except subprocess.TimeoutExpired:
            self._process.terminate()
            self._process.wait(timeout=5)
        if self._process.returncode not in {None, 0}:
            raise self._failure()
