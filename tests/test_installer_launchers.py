from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import install


@pytest.mark.installer
def test_supported_python_policy(monkeypatch) -> None:
    monkeypatch.setattr(install, "python_version", lambda executable: (3, 12, 64))
    install.validate_python("python")
    monkeypatch.setattr(install, "python_version", lambda executable: (3, 13, 64))
    with pytest.raises(SystemExit):
        install.validate_python("python")


@pytest.mark.installer
def test_explicit_directml_and_mps_modes() -> None:
    cuda = install.CudaInfo(False)
    assert install.choose_mode(cuda, "directml", True) == ("directml", "")
    assert install.choose_mode(cuda, "mps", True) == ("mps", "")


@pytest.mark.installer
def test_launchers_resolve_the_repository_and_preserve_arguments() -> None:
    shell = Path("run_gui.sh").read_text(encoding="utf-8")
    batch = Path("run_gui.bat").read_text(encoding="utf-8")
    assert 'script_dir=' in shell
    assert '"$@"' in shell
    assert "%~dp0" in batch
    assert "%*" in batch
    assert "exit /b %errorlevel%" in batch


@pytest.mark.installer
def test_shell_launchers_have_valid_syntax() -> None:
    subprocess.run(["bash", "-n", "install.sh", "run_gui.sh"], check=True)


def test_no_obsolete_binary_builder_or_cli_parser() -> None:
    assert not Path("backend/tools/makedist.py").exists()
    assert not Path("backend/tools/args_handler.py").exists()
    assert not Path("docker/Dockerfile").exists()
