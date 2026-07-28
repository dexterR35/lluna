from __future__ import annotations

import importlib
import os
import subprocess
import sys

from backend.core.build_info import BUILD_INFO
from backend.core.environment import initialize_process_environment


def test_canonical_repository_metadata() -> None:
    assert BUILD_INFO.repository_owner == "dexterR35"
    assert BUILD_INFO.repository_name == "midgard"
    assert BUILD_INFO.project_url == "https://github.com/dexterR35/midgard"
    assert BUILD_INFO.issues_url.endswith("/issues")
    assert BUILD_INFO.releases_url.endswith("/releases")
    assert (
        BUILD_INFO.latest_release_api_url
        == "https://api.github.com/repos/dexterR35/midgard/releases/latest"
    )


def test_environment_initialization_is_explicit_and_idempotent() -> None:
    environ: dict[str, str] = {}
    first = initialize_process_environment(environ)
    second = initialize_process_environment(environ)
    assert environ["KMP_DUPLICATE_LIB_OK"] == "True"
    assert environ["FLAGS_bvar_dump"] == "false"
    assert environ["FLAGS_mbvar_dump"] == "false"
    assert len(first) == 3
    assert second == ()


def test_core_import_does_not_load_qt() -> None:
    code = (
        "import sys; import backend.core.build_info, backend.core.paths; "
        "assert not any(n.startswith(('PySide6', 'qfluentwidgets')) for n in sys.modules)"
    )
    subprocess.run([sys.executable, "-c", code], check=True, env=os.environ.copy())


def test_paths_are_not_cwd_relative(monkeypatch, tmp_path) -> None:
    import backend.core.paths as paths

    monkeypatch.chdir(tmp_path)
    refreshed = importlib.reload(paths)
    assert refreshed.PATHS.config_file.is_absolute()
    assert refreshed.PATHS.project_root.name == "midgard-studio"


def test_frozen_paths_separate_resources_from_writable_state(
    monkeypatch, tmp_path
) -> None:
    import backend.core.paths as paths

    resources = tmp_path / "bundle" / "_internal"
    executable = tmp_path / "bundle" / "Midgard"
    monkeypatch.delenv("MIDGARD_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("MIDGARD_CONFIG_DIR", raising=False)
    monkeypatch.delenv("MIDGARD_MODELS_DIR", raising=False)
    monkeypatch.setattr(paths.sys, "_MEIPASS", str(resources), raising=False)
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "executable", str(executable))

    resolved = paths.AppPaths.resolve()
    assert resolved.project_root == resources
    assert resolved.models_dir == resources / "backend" / "models"
    assert resolved.config_dir == executable.parent / "config"
