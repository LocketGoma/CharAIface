from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


_PROCESS_START_MONOTONIC = time.monotonic()


@dataclass(frozen=True)
class ProcessMetrics:
    pid: int
    process_name: str
    platform: str
    python_version: str
    memory_rss_bytes: int | None
    memory_peak_rss_bytes: int | None
    cpu_percent: float | None
    cpu_sample_seconds: float
    thread_count: int | None
    uptime_seconds: float
    measured_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "process_name": self.process_name,
            "platform": self.platform,
            "python_version": self.python_version,
            "memory_rss_bytes": self.memory_rss_bytes,
            "memory_rss_mb": _bytes_to_mb(self.memory_rss_bytes),
            "memory_peak_rss_bytes": self.memory_peak_rss_bytes,
            "memory_peak_rss_mb": _bytes_to_mb(self.memory_peak_rss_bytes),
            "cpu_percent": self.cpu_percent,
            "cpu_sample_seconds": self.cpu_sample_seconds,
            "thread_count": self.thread_count,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "measured_at": self.measured_at,
        }


def _bytes_to_mb(value: int | None) -> float | None:
    if value is None:
        return None
    return round(value / (1024 * 1024), 1)


def _try_psutil_metrics(sample_seconds: float) -> tuple[int | None, int | None, float | None, int | None]:
    try:
        import psutil  # type: ignore
    except Exception:
        return None, None, None, None

    process = psutil.Process(os.getpid())
    memory = process.memory_info()
    peak_rss = getattr(memory, "peak_wset", None) or getattr(memory, "peak_rss", None)

    cpu_percent: float | None = None
    try:
        process.cpu_percent(interval=None)
        if sample_seconds > 0:
            time.sleep(sample_seconds)
        cpu_percent = round(float(process.cpu_percent(interval=None)), 1)
    except Exception:
        cpu_percent = None

    try:
        thread_count = int(process.num_threads())
    except Exception:
        thread_count = None

    return int(memory.rss), int(peak_rss) if peak_rss else None, cpu_percent, thread_count


def _windows_memory_and_threads() -> tuple[int | None, int | None, int | None]:
    """Best-effort Windows memory lookup without requiring psutil.

    The previous ctypes path could fail silently on some Windows/Python
    combinations when psapi was not resolved as expected. Keep the ctypes
    path, but make it stricter and then fall back to PowerShell Get-Process,
    which is slower but reliable enough for an explicit /systemstatus command.
    """
    if platform.system().lower() != "windows":
        return None, None, None

    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
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
                ("PrivateUsage", ctypes.c_size_t),
            ]

        psapi = ctypes.WinDLL("Psapi.dll")
        kernel32 = ctypes.WinDLL("Kernel32.dll")
        get_current_process = kernel32.GetCurrentProcess
        get_current_process.restype = wintypes.HANDLE
        get_process_memory_info = psapi.GetProcessMemoryInfo
        get_process_memory_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),
            wintypes.DWORD,
        ]
        get_process_memory_info.restype = wintypes.BOOL

        counters = PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
        ok = get_process_memory_info(
            get_current_process(),
            ctypes.byref(counters),
            counters.cb,
        )

        if ok:
            rss = int(counters.WorkingSetSize)
            peak = int(counters.PeakWorkingSetSize)
            _, _, thread_count = _powershell_process_snapshot(os.getpid())
            return rss, peak, thread_count
    except Exception:
        pass

    rss, peak, thread_count = _powershell_process_snapshot(os.getpid())
    return rss, peak, thread_count


def _powershell_process_snapshot(pid: int) -> tuple[int | None, int | None, int | None]:
    """Return WorkingSet64, PeakWorkingSet64, thread count using Get-Process."""
    if platform.system().lower() != "windows":
        return None, None, None

    command = (
        "$p = Get-Process -Id " + str(int(pid)) + " -ErrorAction Stop; "
        "[PSCustomObject]@{"
        "WorkingSet64=$p.WorkingSet64;"
        "PeakWorkingSet64=$p.PeakWorkingSet64;"
        "Threads=$p.Threads.Count"
        "} | ConvertTo-Json -Compress"
    )
    try:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=creation_flags,
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            return None, None, None
        payload = json.loads(completed.stdout.strip())
        rss = payload.get("WorkingSet64")
        peak = payload.get("PeakWorkingSet64")
        threads = payload.get("Threads")
        return (
            int(rss) if rss is not None else None,
            int(peak) if peak is not None else None,
            int(threads) if threads is not None else None,
        )
    except Exception:
        return None, None, None


def _process_cpu_time_seconds() -> float | None:
    if platform.system().lower() == "windows":
        try:
            import ctypes
            from ctypes import wintypes

            creation_time = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel_time = wintypes.FILETIME()
            user_time = wintypes.FILETIME()
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            ok = ctypes.windll.kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation_time),
                ctypes.byref(exit_time),
                ctypes.byref(kernel_time),
                ctypes.byref(user_time),
            )
            if not ok:
                return None

            def filetime_to_int(value) -> int:
                return (int(value.dwHighDateTime) << 32) + int(value.dwLowDateTime)

            return (filetime_to_int(kernel_time) + filetime_to_int(user_time)) / 10_000_000.0
        except Exception:
            return None

    try:
        times = os.times()
        return float(times.user + times.system)
    except Exception:
        return None


def _fallback_cpu_percent(sample_seconds: float) -> float | None:
    if sample_seconds <= 0:
        return None

    cpu_count = os.cpu_count() or 1
    start_cpu = _process_cpu_time_seconds()
    start_time = time.perf_counter()
    if start_cpu is None:
        return _powershell_cpu_percent(os.getpid(), sample_seconds)

    time.sleep(sample_seconds)

    end_cpu = _process_cpu_time_seconds()
    elapsed = time.perf_counter() - start_time
    if end_cpu is None or elapsed <= 0:
        return _powershell_cpu_percent(os.getpid(), sample_seconds)

    return round(max(0.0, (end_cpu - start_cpu) / elapsed / cpu_count * 100.0), 1)


def _powershell_cpu_seconds(pid: int) -> float | None:
    if platform.system().lower() != "windows":
        return None

    command = (
        "$p = Get-Process -Id " + str(int(pid)) + " -ErrorAction Stop; "
        "[PSCustomObject]@{CPU=$p.CPU} | ConvertTo-Json -Compress"
    )
    try:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=creation_flags,
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            return None
        payload = json.loads(completed.stdout.strip())
        value = payload.get("CPU")
        return float(value) if value is not None else 0.0
    except Exception:
        return None


def _powershell_cpu_percent(pid: int, sample_seconds: float) -> float | None:
    start_cpu = _powershell_cpu_seconds(pid)
    start_time = time.perf_counter()
    if start_cpu is None:
        return None

    time.sleep(sample_seconds)

    end_cpu = _powershell_cpu_seconds(pid)
    elapsed = time.perf_counter() - start_time
    if end_cpu is None or elapsed <= 0:
        return None

    cpu_count = os.cpu_count() or 1
    return round(max(0.0, (end_cpu - start_cpu) / elapsed / cpu_count * 100.0), 1)



def _disk_usage_payload(path: str | None = None) -> dict[str, Any]:
    import shutil

    disk_path = path or os.path.abspath(os.sep)
    try:
        usage = shutil.disk_usage(disk_path)
    except Exception:
        return {
            "path": disk_path,
            "total_bytes": None,
            "used_bytes": None,
            "free_bytes": None,
            "percent": None,
        }

    total = int(usage.total)
    used = int(usage.used)
    free = int(usage.free)
    percent = round((used / total * 100.0), 1) if total else None
    return {
        "path": disk_path,
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "percent": percent,
    }


def _try_psutil_system_overview(sample_seconds: float) -> dict[str, Any] | None:
    try:
        import psutil  # type: ignore
    except Exception:
        return None

    try:
        cpu_percent = float(psutil.cpu_percent(interval=max(0.0, sample_seconds)))
    except Exception:
        cpu_percent = None

    try:
        memory = psutil.virtual_memory()
        ram_total = int(memory.total)
        ram_available = int(memory.available)
        ram_used = int(memory.used)
        ram_percent = float(memory.percent)
    except Exception:
        ram_total = ram_available = ram_used = None
        ram_percent = None

    return {
        "platform": f"{platform.system()} {platform.release()}".strip(),
        "cpu_percent": round(cpu_percent, 1) if cpu_percent is not None else None,
        "cpu_count": os.cpu_count(),
        "ram_total_bytes": ram_total,
        "ram_used_bytes": ram_used,
        "ram_available_bytes": ram_available,
        "ram_percent": round(ram_percent, 1) if ram_percent is not None else None,
        "disk": _disk_usage_payload(),
        "measured_at": datetime.now(timezone.utc).isoformat(),
    }


def _windows_system_memory() -> tuple[int | None, int | None, int | None, float | None]:
    if platform.system().lower() != "windows":
        return None, None, None, None

    try:
        import ctypes
        from ctypes import wintypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None, None, None, None

        total = int(status.ullTotalPhys)
        available = int(status.ullAvailPhys)
        used = max(0, total - available)
        percent = float(status.dwMemoryLoad)
        return total, used, available, percent
    except Exception:
        return None, None, None, None


def _macos_system_memory() -> tuple[int | None, int | None, int | None, float | None]:
    if platform.system().lower() != "darwin":
        return None, None, None, None

    try:
        total = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip())
    except Exception:
        total = None

    try:
        page_size = int(subprocess.check_output(["sysctl", "-n", "hw.pagesize"], text=True).strip())
        vm_stat = subprocess.check_output(["vm_stat"], text=True)
        values: dict[str, int] = {}
        for line in vm_stat.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            digits = "".join(ch for ch in value if ch.isdigit())
            if digits:
                values[key.strip()] = int(digits)
        free_pages = values.get("Pages free", 0) + values.get("Pages speculative", 0)
        inactive_pages = values.get("Pages inactive", 0)
        available = (free_pages + inactive_pages) * page_size
        if total is None:
            return None, None, available, None
        used = max(0, total - available)
        percent = round(used / total * 100.0, 1) if total else None
        return total, used, available, percent
    except Exception:
        return total, None, None, None


def _fallback_system_cpu_percent(sample_seconds: float) -> float | None:
    if sample_seconds <= 0:
        return None

    system_name = platform.system().lower()
    if system_name == "windows":
        command = (
            "(Get-Counter '\\Processor(_Total)\\% Processor Time' "
            "-SampleInterval 1 -MaxSamples 1).CounterSamples.CookedValue"
        )
        try:
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                capture_output=True,
                text=True,
                timeout=4,
                creationflags=creation_flags,
            )
            if completed.returncode == 0 and completed.stdout.strip():
                return round(float(completed.stdout.strip()), 1)
        except Exception:
            return None

    return None


def get_system_overview(sample_seconds: float = 0.0) -> dict[str, Any]:
    sample_seconds = max(0.0, float(sample_seconds))
    psutil_payload = _try_psutil_system_overview(sample_seconds)
    if psutil_payload is not None:
        return psutil_payload

    total, used, available, percent = _windows_system_memory()
    if total is None:
        total, used, available, percent = _macos_system_memory()

    cpu_percent = _fallback_system_cpu_percent(sample_seconds)
    return {
        "platform": f"{platform.system()} {platform.release()}".strip(),
        "cpu_percent": cpu_percent,
        "cpu_count": os.cpu_count(),
        "ram_total_bytes": total,
        "ram_used_bytes": used,
        "ram_available_bytes": available,
        "ram_percent": percent,
        "disk": _disk_usage_payload(),
        "measured_at": datetime.now(timezone.utc).isoformat(),
    }


def get_process_status(sample_seconds: float = 0.2) -> dict[str, Any]:
    sample_seconds = max(0.0, float(sample_seconds))
    rss, peak_rss, cpu_percent, thread_count = _try_psutil_metrics(sample_seconds)

    if rss is None:
        rss, peak_rss, thread_count = _windows_memory_and_threads()

    if cpu_percent is None:
        cpu_percent = _fallback_cpu_percent(sample_seconds)

    metrics = ProcessMetrics(
        pid=os.getpid(),
        process_name=os.path.basename(sys.argv[0] or sys.executable),
        platform=f"{platform.system()} {platform.release()}".strip(),
        python_version=platform.python_version(),
        memory_rss_bytes=rss,
        memory_peak_rss_bytes=peak_rss,
        cpu_percent=cpu_percent,
        cpu_sample_seconds=round(sample_seconds, 2),
        thread_count=thread_count,
        uptime_seconds=time.monotonic() - _PROCESS_START_MONOTONIC,
        measured_at=datetime.now(timezone.utc).isoformat(),
    )
    return metrics.to_dict()
