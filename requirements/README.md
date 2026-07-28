# Dependency maintenance

Python 3.12 is the canonical build interpreter. Runtime dependencies stay in
`requirements.txt`; framework variants stay in the root
`requirements-{cpu,cuda,directml,macos}.txt` files so `install.py` remains
compatible during the migration.

For a release, resolve each platform/backend file in a clean Python 3.12
environment, install it with `constraints.txt`, run the full safe test suite,
and archive `python -m pip freeze --all` with the release evidence. Never reuse
a CUDA lock for DirectML, MPS, or CPU.

Packaging dependencies are isolated in `requirements-packaging.txt`. Test and
development tools are isolated in `requirements-test.txt` and
`requirements-dev.txt`.
