"""Aggressive memory management and Darwin libmalloc reclamation for Apple Silicon."""

import ctypes
import gc
import platform
import sys

import mlx.core as mx

_libsystem = ctypes.CDLL("libSystem.B.dylib") if platform.system() == "Darwin" else None
if _libsystem:
    try:
        _libsystem.malloc_zone_pressure_relief.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        _libsystem.malloc_zone_pressure_relief.restype = ctypes.c_size_t
    except AttributeError:
        _libsystem = None


def configure_mlx_budget(cache_limit_mb: int = 64, memory_limit_mb: int = 1280) -> None:
    """Cap MLX BufferCache so transient activation tensors don't stay pinned in Unified Memory."""
    try:
        mx.set_cache_limit(cache_limit_mb * 1024 * 1024)
        mx.set_memory_limit(memory_limit_mb * 1024 * 1024)
    except Exception:
        pass


def reclaim_idle_memory(torch_module=None) -> int:
    """Flush Python GC, MLX Metal BufferCache, PyTorch MPS pool, and macOS libmalloc zones.

    Returns the number of bytes relieved by Darwin libmalloc.
    """
    gc.collect()
    try:
        mx.clear_cache()
    except Exception:
        pass

    target_torch = torch_module or sys.modules.get("torch")
    if target_torch is not None:
        try:
            if hasattr(target_torch, "backends") and target_torch.backends.mps.is_available():
                target_torch.mps.synchronize()
                target_torch.mps.empty_cache()
        except Exception:
            pass

    relieved_bytes = 0
    if _libsystem is not None:
        try:
            # 0 releases all purgeable heap zones back to macOS XNU kernel
            relieved_bytes = int(_libsystem.malloc_zone_pressure_relief(None, 0))
        except Exception:
            relieved_bytes = 0

    return relieved_bytes
