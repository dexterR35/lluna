from __future__ import annotations
import json, shutil, subprocess, sys
from pathlib import Path
import pytest
import install

@pytest.mark.installer
def test_supported_python_policy(monkeypatch):
    monkeypatch.setattr(install,"python_version",lambda executable:(3,12,64));install.validate_python("python")
    monkeypatch.setattr(install,"python_version",lambda executable:(3,13,64))
    with pytest.raises(SystemExit):install.validate_python("python")

def test_explicit_hardware_modes():
    cuda=install.CudaInfo(False)
    assert install.choose_mode(cuda,"directml",True)==("directml","")
    assert install.choose_mode(cuda,"mps",True)==("mps","")

def test_onnxruntime_gpu_package_matches_torch_cuda_major():
    assert install.onnxruntime_gpu_install_args("cu118")==["onnxruntime-gpu==1.20.1","--index-url",install.ORT_CUDA11_INDEX]
    assert install.onnxruntime_gpu_install_args("cu126")==["onnxruntime-gpu==1.22.0"]

def test_source_installer_bootstraps_electron_not_legacy_launchers():
    source=Path("install.py").read_text(encoding="utf-8")
    assert '"install", "--allow-git=all"' in source
    assert "install_desktop_dependencies()" in source
    assert not Path("gui.py").exists();assert not Path("ui").exists();assert not Path("run_gui.sh").exists();assert not Path("run_gui.bat").exists()

def test_project_runtime_versions_are_declared():
    assert Path(".python-version").read_text().strip().startswith("3.12.")
    package=json.loads(Path("package.json").read_text());assert int(package["engines"]["node"].removeprefix(">="))>=22

@pytest.mark.installer
def test_source_install_shell_has_valid_syntax():
    if sys.platform=="win32":pytest.skip("POSIX syntax is checked on Linux")
    bash=shutil.which("bash")
    if bash is None:pytest.skip("bash unavailable")
    subprocess.run([bash,"-n","install.sh"],check=True)
