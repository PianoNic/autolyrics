import os
import sys


class BackgroundPriority:
    """Runs the process below normal priority and caps the CPU threads of the ML libraries:
    separation and alignment are background work and must not make the desktop stutter."""

    BELOW_NORMAL = 0x00004000  # Windows priority class

    def __init__(self, threads: int | None = None):
        cores = os.cpu_count() or 4
        self._threads = threads or max(2, min(6, cores // 3))

    def apply(self) -> None:
        for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
            os.environ.setdefault(name, str(self._threads))
        try:
            if sys.platform == "win32":
                import ctypes

                kernel32 = ctypes.windll.kernel32
                kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), self.BELOW_NORMAL)
            else:
                os.nice(5)
        except (OSError, AttributeError):
            pass
        try:
            import torch

            torch.set_num_threads(self._threads)
        except ImportError:
            pass
