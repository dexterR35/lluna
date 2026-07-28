from pathlib import Path


def test_backend_main_has_no_public_cli_entrypoint() -> None:
    source = Path("backend/main.py").read_text(encoding="utf-8")
    assert "__name__ == '__main__'" not in source
    assert "parse_args" not in source
    assert "_run_bg_remove_cli" not in source
    assert "backend.pipelines.subtitle import SubtitleRemover" in source
    assert not Path("backend/tools/subtitle_remover_remote_call.py").exists()


def test_readme_does_not_advertise_binary_packaging_or_media_cli() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "QPT" not in readme
    assert "backend/main.py -i" not in readme
    assert "Windows package build" not in readme
