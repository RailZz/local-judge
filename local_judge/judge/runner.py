import os
import contextlib
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Callable, Generator, List, Optional, Tuple

def _rss_bytes(pid: int) -> int:
    """Return RSS bytes using platform-specific methods."""
    if os.name == "nt":
        try:
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

            psapi = ctypes.windll.psapi
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_INFORMATION = 0x0400
            PROCESS_VM_READ = 0x0010
            handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
            if not handle:
                return 0
            try:
                counters = PROCESS_MEMORY_COUNTERS()
                counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
                if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                    return int(counters.WorkingSetSize)
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return 0
        return 0
    # Linux/Unix via /proc
    try:
        with open(f"/proc/{pid}/status", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        return int(parts[1]) * 1024
    except Exception:
        pass
    # Optional psutil fallback if available
    try:
        import psutil  # type: ignore
        return int(psutil.Process(pid).memory_info().rss)
    except Exception:
        return 0


@dataclass
class JudgeConfig:
    solution_path: str
    language: Optional[str]  # "Python" | "C" | "C++" | None for auto
    tests_dir: str
    input_pattern: str  # e.g., "{num}.in"
    ans_pattern: str  # e.g., "{num}.out" or "{num}.a"
    checker_path: Optional[str]
    checker_args_template: Optional[str]  # e.g., "{in} {ans} {out}"
    time_limit_s: float
    memory_limit_mb: int
    ignore_whitespace: bool


@dataclass
class JudgeResult:
    test_id: str
    verdict: str  # AC, WA, TLE, MLE, RTE, CE
    time_ms: int
    memory_mb: float
    details: Optional[str] = None


class JudgeRunner:
    def __init__(self) -> None:
        self._compiled_exe: Optional[str] = None

    def prepare(self, cfg: JudgeConfig) -> Optional[str]:
        lang = self._detect_language(cfg.solution_path, cfg.language)
        if lang in ("C", "C++"):
            exe_path = os.path.join(tempfile.gettempdir(), f"local_judge_{int(time.time())}")
            cmd = self._compile_command(lang, cfg.solution_path, exe_path)
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            if proc.returncode != 0:
                return proc.stdout
            self._compiled_exe = exe_path
        else:
            self._compiled_exe = None
        return None

    def run_all(self, cfg: JudgeConfig, on_progress: Optional[Callable[[JudgeResult], None]] = None) -> Generator[JudgeResult, None, None]:
        lang = self._detect_language(cfg.solution_path, cfg.language)
        tests = self._discover_tests(cfg.tests_dir, cfg.input_pattern, cfg.ans_pattern)
        for test_id, in_path, ans_path in tests:
            result = self._run_one(cfg, lang, test_id, in_path, ans_path)
            if on_progress:
                on_progress(result)
            yield result

    def _detect_language(self, path: str, override: Optional[str]) -> str:
        if override in ("Python", "C", "C++"):
            return override
        ext = os.path.splitext(path)[1].lower()
        if ext == ".py":
            return "Python"
        if ext == ".c":
            return "C"
        if ext in (".cc", ".cpp", ".cxx"):
            return "C++"
        # Default to Python
        return "Python"

    def _compile_command(self, lang: str, src: str, out: str) -> List[str]:
        if lang == "C":
            return ["gcc", "-std=c11", "-O2", "-pipe", "-s", src, "-o", out]
        return ["g++", "-std=gnu++17", "-O2", "-pipe", "-s", src, "-o", out]

    def _discover_tests(self, directory: str, in_pat: str, ans_pat: str) -> List[Tuple[str, str, Optional[str]]]:
        # Convert {num} -> (\d+)
        in_regex = re.escape(in_pat).replace(re.escape("{num}"), r"(\d+)")
        pattern = re.compile(f"^{in_regex}$")
        tests: List[Tuple[str, str, Optional[str]]] = []
        for name in sorted(os.listdir(directory)):
            match = pattern.match(name)
            if not match:
                continue
            num_str = match.group(1)
            in_path = os.path.join(directory, name)
            ans_name = ans_pat.replace("{num}", num_str)
            ans_path = os.path.join(directory, ans_name)
            if not os.path.exists(ans_path):
                ans_path = None
            tests.append((num_str, in_path, ans_path))
        return tests

    def _build_run_command(self, lang: str, cfg: JudgeConfig) -> List[str]:
        if lang == "Python":
            return [sys.executable, cfg.solution_path]
        if lang in ("C", "C++") and self._compiled_exe:
            return [self._compiled_exe]
        # Fallback
        return [cfg.solution_path]

    def _set_resource_limits(self, memory_limit_mb: int, time_limit_s: float) -> None:
        try:
            import resource  # type: ignore

            # Address space (virtual memory)
            bytes_limit = memory_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (bytes_limit, bytes_limit))
            # CPU time limit (seconds)
            cpu_seconds = max(1, int(time_limit_s))
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        except Exception:
            pass

    def _compare_outputs(self, produced: str, expected: str, ignore_ws: bool) -> bool:
        try:
            with open(produced, "r", encoding="utf-8", errors="replace") as f1:
                out_text = f1.read()
            with open(expected, "r", encoding="utf-8", errors="replace") as f2:
                ans_text = f2.read()
        except Exception:
            return False
        if ignore_ws:
            def norm(s: str) -> str:
                return "\n".join(line.rstrip() for line in s.strip().splitlines())

            return norm(out_text) == norm(ans_text)
        return out_text == ans_text

    def _invoke_checker(self, checker_path: str, args_template: Optional[str], in_path: str, ans_path: Optional[str], out_path: str, time_limit_s: float) -> Tuple[bool, str]:
        args_template = args_template or "{in} {ans} {out}"
        args_str = args_template.replace("{in}", shlex.quote(in_path)).replace("{out}", shlex.quote(out_path)).replace("{ans}", shlex.quote(ans_path or ""))
        cmd = f"{shlex.quote(checker_path)} {args_str}".strip()
        try:
            proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=max(1.0, time_limit_s * 2))
            ok = proc.returncode == 0
            details = (proc.stdout + ("\n" + proc.stderr if proc.stderr else "")).strip()
            return ok, details
        except subprocess.TimeoutExpired:
            return False, "Checker timed out"
        except Exception as e:
            return False, f"Checker error: {e}"

    def _run_one(self, cfg: JudgeConfig, lang: str, test_id: str, in_path: str, ans_path: Optional[str]) -> JudgeResult:
        cmd = self._build_run_command(lang, cfg)
        tmp_dir = tempfile.mkdtemp(prefix="judge_")
        out_path = os.path.join(tmp_dir, f"{test_id}.out")

        with open(in_path, "rb") as fin, open(out_path, "wb") as fout:
            try:
                start = time.perf_counter()
                kwargs = {
                    "stdin": fin,
                    "stdout": fout,
                    "stderr": subprocess.PIPE,
                }
                if os.name != "nt":
                    kwargs["preexec_fn"] = lambda: self._set_resource_limits(cfg.memory_limit_mb, cfg.time_limit_s)
                proc = subprocess.Popen(cmd, **kwargs)
            except FileNotFoundError as e:
                return JudgeResult(test_id=test_id, verdict="CE", time_ms=0, memory_mb=0.0, details=str(e))
            except Exception as e:
                return JudgeResult(test_id=test_id, verdict="RTE", time_ms=0, memory_mb=0.0, details=str(e))

            peak_rss = 0
            timed_out = False
            mem_exceeded = False
            poll_interval = 0.01
            wall_deadline = start + cfg.time_limit_s

            try:
                while True:
                    if time.perf_counter() > wall_deadline:
                        timed_out = True
                        break
                    rss = _rss_bytes(proc.pid)
                    if rss > peak_rss:
                        peak_rss = rss
                    if rss > cfg.memory_limit_mb * 1024 * 1024 and rss > 0:
                        mem_exceeded = True
                        break
                    if proc.poll() is not None:
                        break
                    time.sleep(poll_interval)
            finally:
                if timed_out:
                    with contextlib.suppress(Exception):
                        proc.kill()
                if mem_exceeded:
                    with contextlib.suppress(Exception):
                        proc.kill()

            try:
                _, stderr = proc.communicate(timeout=0.2)
            except Exception:
                stderr = b""

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        mem_mb = peak_rss / (1024 * 1024)

        if timed_out:
            return JudgeResult(test_id=test_id, verdict="TLE", time_ms=elapsed_ms, memory_mb=mem_mb)
        if mem_exceeded:
            return JudgeResult(test_id=test_id, verdict="MLE", time_ms=elapsed_ms, memory_mb=mem_mb)

        if proc.returncode != 0:
            details = stderr.decode(errors="replace").strip()
            return JudgeResult(test_id=test_id, verdict="RTE", time_ms=elapsed_ms, memory_mb=mem_mb, details=details)

        # Compare outputs
        if cfg.checker_path:
            ok, details = self._invoke_checker(cfg.checker_path, cfg.checker_args_template, in_path, ans_path, out_path, cfg.time_limit_s)
            verdict = "AC" if ok else "WA"
            return JudgeResult(test_id=test_id, verdict=verdict, time_ms=elapsed_ms, memory_mb=mem_mb, details=details)
        else:
            if ans_path is None:
                return JudgeResult(test_id=test_id, verdict="AC", time_ms=elapsed_ms, memory_mb=mem_mb, details="No answer file; checker not provided")
            ok = self._compare_outputs(out_path, ans_path, cfg.ignore_whitespace)
            verdict = "AC" if ok else "WA"
            return JudgeResult(test_id=test_id, verdict=verdict, time_ms=elapsed_ms, memory_mb=mem_mb)

