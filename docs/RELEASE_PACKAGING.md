# Release packaging

`packaging/backend-sidecar.spec` builds a windowless `midgard-backend` PyInstaller onedir. `frontend/forge.config.js` copies only that frozen directory into Electron resources as `backend-sidecar`; Python source and global runtimes are not assumed on user machines. Forge creates platform-native makers.

```bash
.venv/bin/python -m pip install -r requirements-packaging.txt
npm ci --allow-git=all
python packaging/build.py --validate-only
python packaging/build.py --clean --profile cpu
```

User configuration, autosaves, artifacts, logs, downloads, cache, and optional models are under OS user-data roots, never inside ASAR or sidecar resources. The release CI matrix currently packages Windows CPU, Linux CPU, and macOS MPS. Signing/notarization credentials and clean-machine smoke tests remain release gates; see implementation status.

For repeatable/offline shell packaging, set `MIDGARD_ELECTRON_ZIP_DIR` to a directory containing the official `electron-v<version>-<platform>-<arch>.zip`; Forge passes it to Electron Packager without network access.
