# Midgard Docker image - package install mirrors install.py (torch / paddle / ORT).
FROM python:3.12

RUN --mount=type=cache,target=/root/.cache,sharing=private \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        # pyside6 / Qt
        libegl1 libxkbcommon0 libdbus-1-3 \
        libxcb-cursor0 \
        && \
    rm -rf /var/lib/apt/lists/*

ADD . /midgard
WORKDIR /midgard

# Keep versions in sync with install.py
ARG TORCH_VERSION=2.7.0
ARG TORCHVISION_VERSION=0.22.0
ARG PADDLE_VERSION=3.0.0
ARG CUDA_VERSION=11.8
ARG HARDWARD_ACCELERATOR=cuda

ENV PADDLE_CPU_INDEX=https://www.paddlepaddle.org.cn/packages/stable/cpu/
ENV PADDLE_CU118_INDEX=https://www.paddlepaddle.org.cn/packages/stable/cu118/
ENV ORT_CUDA11_INDEX=https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-11/pypi/simple/

RUN --mount=type=cache,target=/root/.cache/pip,sharing=private \
    set -eux; \
    pip install --upgrade pip setuptools wheel; \
    case "${HARDWARD_ACCELERATOR}" in \
      cuda) \
        CUDA_TAG="cu$(echo "${CUDA_VERSION}" | tr -d '.')"; \
        if [ "${CUDA_VERSION}" = "11.8" ]; then \
          pip install "paddlepaddle-gpu==${PADDLE_VERSION}" -i "${PADDLE_CU118_INDEX}"; \
          pip install \
            "torch==${TORCH_VERSION}" \
            "torchvision==${TORCHVISION_VERSION}" \
            --index-url "https://download.pytorch.org/whl/${CUDA_TAG}"; \
          pip install -r /midgard/requirements.txt; \
          pip uninstall -y onnxruntime onnxruntime-gpu || true; \
          pip install onnxruntime-gpu==1.20.1 --index-url "${ORT_CUDA11_INDEX}"; \
          pip install setuptools==80.4.0; \
        else \
          pip install "paddlepaddle==${PADDLE_VERSION}" -i "${PADDLE_CPU_INDEX}"; \
          pip install \
            "torch==${TORCH_VERSION}" \
            "torchvision==${TORCHVISION_VERSION}" \
            --index-url "https://download.pytorch.org/whl/${CUDA_TAG}"; \
          pip install -r /midgard/requirements.txt; \
          pip uninstall -y onnxruntime || true; \
          pip install onnxruntime-gpu==1.22.0; \
        fi \
        ;; \
      directml) \
        pip install "paddlepaddle==${PADDLE_VERSION}" -i "${PADDLE_CPU_INDEX}"; \
        pip install torch_directml==0.2.5.dev240914; \
        pip install -r /midgard/requirements.txt; \
        pip uninstall -y onnxruntime onnxruntime-gpu || true; \
        pip install onnxruntime-directml==1.20.1; \
        ;; \
      cpu) \
        pip install "paddlepaddle==${PADDLE_VERSION}" -i "${PADDLE_CPU_INDEX}"; \
        pip install \
          "torch==${TORCH_VERSION}" \
          "torchvision==${TORCHVISION_VERSION}" \
          --index-url https://download.pytorch.org/whl/cpu; \
        pip install -r /midgard/requirements.txt; \
        pip install onnxruntime; \
        sed -i 's/HARDWARE_ACCELERATION_OPTION *= *.*/HARDWARE_ACCELERATION_OPTION = False/g' /midgard/backend/config.py; \
        ;; \
      *) \
        echo "Unknown HARDWARD_ACCELERATOR=${HARDWARD_ACCELERATOR}" >&2; \
        exit 1; \
        ;; \
    esac; \
    # Match install.py extras (also listed in requirements.txt)
    pip install "rembg>=2.0.60" "transformers>=4.48.0" "huggingface_hub>=0.26.0" \
        "diffusers>=0.37.1" "accelerate>=1.0.0"

# Merge split core weights (big-lama / ProPainter) when parts are present
RUN python -c "from install import verify_models; verify_models()"

# Prefetch default Remove BG / Enhance ×2 / Select Object (same as install.py)
ARG PREFETCH_MODELS=1
RUN --mount=type=cache,target=/root/.cache,sharing=private \
    set -eux; \
    if [ "${PREFETCH_MODELS}" != "1" ]; then \
      echo "Skipping model prefetch (PREFETCH_MODELS=${PREFETCH_MODELS})"; \
      exit 0; \
    fi; \
    python -c "from pathlib import Path; import sys; \
sys.path.insert(0, '/midgard'); \
from install import prefetch_rembg_models, prefetch_enhance_x2, prefetch_low_light_mirnet, prefetch_select_object_defaults; \
py = Path(sys.executable); \
prefetch_rembg_models(py); \
prefetch_enhance_x2(py); \
prefetch_low_light_mirnet(py); \
prefetch_select_object_defaults(py)"

ENV LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib/
ENV LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib/python3.12/site-packages/nvidia/cuda_runtime/lib/
ENV LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib/python3.12/site-packages/nvidia/cuda_nvrtc/lib/
ENV HF_HOME=/midgard/backend/models/select_object/.hf_cache

CMD ["python", "/midgard/backend/main.py"]
