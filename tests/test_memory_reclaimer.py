"""Tests for aggressive Darwin memory reclaimer and MLX budget configuration."""

from selene.memory_reclaimer import configure_mlx_budget, reclaim_idle_memory


def test_configure_mlx_budget():
    configure_mlx_budget(cache_limit_mb=64, memory_limit_mb=1024)
    # Re-running with different values shouldn't raise
    configure_mlx_budget(cache_limit_mb=128, memory_limit_mb=2048)


def test_reclaim_idle_memory():
    # Should run cleanly and return non-negative integer
    relieved = reclaim_idle_memory()
    assert isinstance(relieved, int)
    assert relieved >= 0
