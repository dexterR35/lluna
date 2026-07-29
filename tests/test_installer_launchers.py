from __future__ import annotations

import shutil
import subprocess
import sys
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


def test_onnxruntime_gpu_package_matches_torch_cuda_major() -> None:
    assert install.onnxruntime_gpu_install_args("cu118") == [
        "onnxruntime-gpu==1.20.1",
        "--index-url",
        install.ORT_CUDA11_INDEX,
    ]
    assert install.onnxruntime_gpu_install_args("cu126") == ["onnxruntime-gpu==1.22.0"]
    assert install.onnxruntime_gpu_install_args("cu128") == ["onnxruntime-gpu==1.22.0"]


def test_torch_backend_match_requires_the_selected_profile(monkeypatch) -> None:
    monkeypatch.setattr(
        install,
        "installed_torch_backend",
        lambda py: ("cuda", "cu126"),
    )

    assert install.torch_backend_matches(Path("python"), "cuda", "cu126")
    assert not install.torch_backend_matches(Path("python"), "cuda", "cu118")
    assert not install.torch_backend_matches(Path("python"), "cpu", "")


@pytest.mark.installer
def test_launchers_resolve_the_repository_and_preserve_arguments() -> None:
    shell = Path("run_gui.sh").read_text(encoding="utf-8")
    batch = Path("run_gui.bat").read_text(encoding="utf-8")
    assert "script_dir=" in shell
    assert '"$@"' in shell
    assert "%~dp0" in batch
    assert "%*" in batch
    assert "exit /b %errorlevel%" in batch
    assert "sys.version_info[:2] == (3, 12)" in shell
    assert "sys.version_info[:2] == (3, 12)" in batch
    assert "midgard.py" in batch


def test_project_python_version_is_pinned_to_312() -> None:
    assert Path(".python-version").read_text(encoding="utf-8").strip().startswith("3.12.")


@pytest.mark.installer
def test_windows_installer_verifies_candidates_and_supports_uv_python() -> None:
    batch = Path("install.bat").read_text(encoding="utf-8")
    assert 'set "PYTHONUTF8=1"' in batch
    assert "sys.version_info[:2] == (3, 12)" in batch
    assert "py -0" in batch
    assert "py %MIDGARD_PY_TAG% install.py %*" in batch
    assert "uv python find 3.12" in batch
    assert '"%MIDGARD_UV_PYTHON%" install.py %*' in batch


@pytest.mark.installer
def test_shell_launchers_have_valid_syntax() -> None:
    if sys.platform == "win32":
        pytest.skip("POSIX shell syntax is validated by the Linux launcher job")
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not available on this platform")
    subprocess.run(  # noqa: S603
        [
            bash,
            "-n",
            "install.sh",
            "run_gui.sh",
            "packaging/linux/install_bundle.sh",
            "packaging/macos/create_dmg.sh",
        ],
        check=True,
    )


def test_frozen_linux_installer_has_progress_log_and_no_python_bootstrap() -> None:
    script = Path("packaging/linux/install_bundle.sh").read_text(encoding="utf-8")
    assert "progress 100" in script
    assert "installer.log" in script
    assert "Python 3.12 is embedded" in script
    assert "pip install" not in script


def test_windows_installer_has_native_progress_log_and_embedded_python() -> None:
    installer = Path("packaging/windows/Midgard.iss").read_text(encoding="utf-8")
    assert "SetupLogging=yes" in installer
    assert "WizardForm.StatusLabel.Caption" in installer
    assert "embedded in this package" in installer
    assert "installer.log" in installer
    assert "pip install" not in installer


def test_macos_dmg_documents_embedded_python_and_first_launch_log() -> None:
    script = Path("packaging/macos/create_dmg.sh").read_text(encoding="utf-8")
    instructions = Path("packaging/macos/INSTALL.txt").read_text(encoding="utf-8")
    assert "Read Me.txt" in script
    assert "Python 3.12 is already embedded" in instructions
    assert "install.log" in instructions
    assert "pip install" not in instructions


def test_no_obsolete_binary_builder_or_cli_parser() -> None:
    assert not Path("backend/tools/makedist.py").exists()
    assert not Path("backend/tools/args_handler.py").exists()
    assert not Path("docker/Dockerfile").exists()
