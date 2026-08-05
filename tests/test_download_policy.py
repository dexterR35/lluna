from pathlib import Path


def test_control_plane_recovery_does_not_seed_optional_downloads() -> None:
    source = Path("backend/tools/shared/download_lifecycle.py").read_text(encoding="utf-8")
    function = source.split("def prepare_restart_pending", 1)[1]
    assert "seed_first_run_downloads(" not in function


def test_control_plane_bootstrap_runs_model_download_recovery() -> None:
    source = Path("backend/application/bootstrap.py").read_text(encoding="utf-8")
    assert "prepare_restart_pending()" in source
