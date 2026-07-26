"""Gather lightweight PC / runtime info for the home dashboard."""

from __future__ import annotations

import getpass
import os
import platform
import socket
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache


@dataclass(frozen=True)
class SystemInfo:
    username: str
    hostname: str
    os_name: str
    cpu: str
    ram: str
    gpu: str
    accelerator: str


def display_name() -> str:
    """Best-effort friendly user name for greeting."""
    for key in ("USER", "USERNAME", "LOGNAME"):
        val = os.environ.get(key)
        if val:
            return val.split("@")[0]
    try:
        return getpass.getuser()
    except Exception:
        return "there"


def greeting_for_now(now: datetime | None = None) -> str:
    h = (now or datetime.now()).hour
    if h < 12:
        return "morning"
    if h < 18:
        return "afternoon"
    return "evening"


def _ram_summary() -> str:
    """Total + available RAM without requiring psutil."""
    try:
        if platform.system() == "Linux":
            total = avail = None
            with open("/proc/meminfo", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        total = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        avail = int(line.split()[1])
                    if total is not None and avail is not None:
                        break
            if total:
                total_gb = total / (1024 * 1024)
                if avail is not None:
                    return f"{avail / (1024 * 1024):.1f} / {total_gb:.1f} GB free"
                return f"{total_gb:.1f} GB"
        if platform.system() == "Darwin":
            import subprocess

            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
            return f"{int(out) / (1024 ** 3):.1f} GB"
        if platform.system() == "Windows":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            total_gb = stat.ullTotalPhys / (1024 ** 3)
            avail_gb = stat.ullAvailPhys / (1024 ** 3)
            return f"{avail_gb:.1f} / {total_gb:.1f} GB free"
    except Exception:
        pass
    return "-"


def _cpu_summary() -> str:
    cores = os.cpu_count() or 0
    name = platform.processor() or ""
    if not name or name.strip() in ("", "x86_64", "i386", "arm", "aarch64"):
        # Linux: try /proc/cpuinfo model name
        try:
            if platform.system() == "Linux":
                with open("/proc/cpuinfo", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("model name"):
                            name = line.split(":", 1)[1].strip()
                            break
        except Exception:
            name = platform.machine() or "CPU"
    name = (name or "CPU").strip()
    if len(name) > 42:
        name = name[:39] + "…"
    return f"{name} · {cores} cores" if cores else name


def _gpu_summary() -> tuple[str, str]:
    """Return (gpu_label, accelerator_label)."""
    accel = "CPU"
    gpu = "CPU only"
    try:
        from backend.tools.hardware_accelerator import HardwareAccelerator

        hw = HardwareAccelerator.instance()
        accel = hw.accelerator_name
        if hw.has_cuda():
            import torch

            gpu = torch.cuda.get_device_name(0)
            vram = hw.get_available_vram_mb()
            if vram > 0:
                gpu = f"{gpu} · {vram / 1024:.1f} GB free"
        elif hw.has_mps():
            gpu = "Apple Metal (MPS)"
        elif accel not in ("CPU",):
            gpu = accel
    except Exception:
        pass
    if len(gpu) > 48:
        gpu = gpu[:45] + "…"
    return gpu, accel


@lru_cache(maxsize=1)
def collect_system_info() -> SystemInfo:
    os_label = f"{platform.system()} {platform.release()}"
    if len(os_label) > 36:
        os_label = os_label[:33] + "…"
    try:
        host = socket.gethostname()
    except Exception:
        host = "-"
    gpu, accel = _gpu_summary()
    return SystemInfo(
        username=display_name(),
        hostname=host,
        os_name=os_label,
        cpu=_cpu_summary(),
        ram=_ram_summary(),
        gpu=gpu,
        accelerator=accel,
    )


@dataclass(frozen=True)
class AppResourceSample:
    """Live app RAM + CPU/GPU usage for the sidebar meter."""

    ram_mb: float
    cpu_percent: float | None
    gpu_used_mb: float | None
    gpu_total_mb: float | None


_cpu_sample: tuple[float, float] | None = None  # (monotonic_s, cpu_seconds)


def _rss_mb_for_pid(pid: int) -> float:
    """Resident set size in MiB for one process (0 on failure)."""
    try:
        if platform.system() == "Linux":
            with open(f"/proc/{pid}/status", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) / 1024.0
        elif platform.system() == "Darwin":
            import subprocess

            out = subprocess.check_output(
                ["ps", "-o", "rss=", "-p", str(pid)], text=True
            ).strip()
            return int(out) / 1024.0
        elif platform.system() == "Windows":
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            GetCurrentProcess = ctypes.windll.kernel32.GetCurrentProcess
            GetProcessMemoryInfo = ctypes.windll.psapi.GetProcessMemoryInfo
            OpenProcess = ctypes.windll.kernel32.OpenProcess
            CloseHandle = ctypes.windll.kernel32.CloseHandle
            PROCESS_QUERY_INFORMATION = 0x0400
            PROCESS_VM_READ = 0x0010
            handle = (
                GetCurrentProcess()
                if pid == os.getpid()
                else OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
            )
            if not handle:
                return 0.0
            try:
                counters = PROCESS_MEMORY_COUNTERS()
                counters.cb = ctypes.sizeof(counters)
                if GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                    return counters.WorkingSetSize / (1024 * 1024)
            finally:
                if pid != os.getpid():
                    CloseHandle(handle)
    except Exception:
        pass
    return 0.0


def _tracked_pids() -> list[int]:
    pids = [os.getpid()]
    try:
        from backend.tools.process_manager import ProcessManager

        for proc in ProcessManager.instance().processes.values():
            if isinstance(proc, int):
                pids.append(proc)
            else:
                pid = getattr(proc, "pid", None)
                if isinstance(pid, int) and pid > 0:
                    pids.append(pid)
    except Exception:
        pass
    # Deduplicate while preserving order
    seen: set[int] = set()
    out: list[int] = []
    for pid in pids:
        if pid not in seen:
            seen.add(pid)
            out.append(pid)
    return out


def _app_ram_mb() -> float:
    return sum(_rss_mb_for_pid(pid) for pid in _tracked_pids())


def _process_cpu_seconds(pid: int) -> float | None:
    try:
        if platform.system() == "Linux":
            with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
                parts = f.read().split()
            hz = os.sysconf("SC_CLK_TCK") or 100
            return (int(parts[13]) + int(parts[14])) / float(hz)
        if platform.system() == "Darwin":
            import subprocess

            out = subprocess.check_output(
                ["ps", "-o", "time=", "-p", str(pid)], text=True
            ).strip()
            # [[dd-]hh:]mm:ss
            days = 0
            if "-" in out:
                day_part, out = out.split("-", 1)
                days = int(day_part)
            bits = [int(x) for x in out.split(":")]
            if len(bits) == 3:
                h, m, s = bits
            elif len(bits) == 2:
                h, m, s = 0, bits[0], bits[1]
            else:
                return None
            return days * 86400 + h * 3600 + m * 60 + s
    except Exception:
        return None
    return None


def _app_cpu_percent() -> float | None:
    """Approx. total CPU % across tracked processes (100% = one core)."""
    global _cpu_sample
    import time

    total_cpu = 0.0
    any_ok = False
    for pid in _tracked_pids():
        sec = _process_cpu_seconds(pid)
        if sec is None:
            continue
        total_cpu += sec
        any_ok = True
    if not any_ok:
        return None
    now = time.monotonic()
    prev = _cpu_sample
    _cpu_sample = (now, total_cpu)
    if prev is None:
        return None
    dt = now - prev[0]
    if dt <= 0.05:
        return None
    return max(0.0, (total_cpu - prev[1]) / dt * 100.0)


def _gpu_used_mb() -> tuple[float | None, float | None]:
    try:
        from backend.tools.hardware_accelerator import HardwareAccelerator

        hw = HardwareAccelerator.instance()
        if not hw.has_cuda():
            return None, None
        free_mb, total_mb = hw.get_vram_mb()
        if total_mb <= 0:
            return None, None
        return max(0.0, total_mb - free_mb), total_mb
    except Exception:
        return None, None


def format_bytes_short(mb: float) -> str:
    """Compact MiB/GiB label for the nav meter."""
    if mb >= 1024:
        return f"{mb / 1024:.1f}G"
    if mb >= 100:
        return f"{mb:.0f}M"
    return f"{mb:.0f}M"


def sample_app_resources() -> AppResourceSample:
    """Lightweight live sample for the sidebar resource meter."""
    gpu_used, gpu_total = _gpu_used_mb()
    return AppResourceSample(
        ram_mb=_app_ram_mb(),
        cpu_percent=_app_cpu_percent(),
        gpu_used_mb=gpu_used,
        gpu_total_mb=gpu_total,
    )
