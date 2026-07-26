FROM python:3.12

RUN --mount=type=cache,target=/root/.cache,sharing=private \
    apt update && \
    apt install -y libgl1-mesa-glx \
        # pyside6
        libegl1 libxkbcommon0 libdbus-1-3 && \
    true

ADD . /midgard
ARG CUDA_VERSION=11.8
ARG HARDWARD_ACCELERATOR="cuda"

# CUDA 12.x specific setup
RUN --mount=type=cache,target=/root/.cache,sharing=private \
    if [ "${HARDWARD_ACCELERATOR}" = "cuda" ] && [ "${CUDA_VERSION}" != "11.8" ]; then \
        pip install paddlepaddle==3.0 && \
        pip install torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cu$(echo ${CUDA_VERSION} | tr -d '.') && \
        pip install -r /midgard/requirements.txt; \
    fi

# CUDA 11.8 specific setup
RUN --mount=type=cache,target=/root/.cache,sharing=private \
if [ "${HARDWARD_ACCELERATOR}" = "cuda" ] && [ "${CUDA_VERSION}" = "11.8" ]; then \
    pip install paddlepaddle==3.0 && \
    pip install torch==2.3.1 torchvision==0.18.1 --index-url https://download.pytorch.org/whl/cu$(echo ${CUDA_VERSION} | tr -d '.') && \
    pip install -r /midgard/requirements.txt && \
    pip uninstall -y onnxruntime-gpu && \
    pip install onnxruntime-gpu==1.20.1 --index-url https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-11/pypi/simple/ && \
    # for paddle
    pip install setuptools==80.4.0; \
fi

# DirectML specific setup
RUN --mount=type=cache,target=/root/.cache,sharing=private \
    if [ "${HARDWARD_ACCELERATOR}" = "directml" ]; then \
        pip install paddlepaddle==3.0 && \
        pip install torch_directml==0.2.5.dev240914 && \
        pip install -r /midgard/requirements.txt; \
    fi

# CPU specific setup
RUN --mount=type=cache,target=/root/.cache,sharing=private \
    if [ "${HARDWARD_ACCELERATOR}" = "cpu" ]; then \
        pip install paddlepaddle==3.0 && \
        pip install -r /midgard/requirements.txt && \
        sed -i 's/HARDWARD_ACCELERATION_OPTION *= *.*/HARDWARD_ACCELERATION_OPTION = False/g' /midgard/backend/config.py; \
    fi

ENV LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib/
ENV LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib/python3.12/site-packages/nvidia/cuda_runtime/lib/
ENV LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib/python3.12/site-packages/nvidia/cuda_nvrtc/lib/
WORKDIR /midgard
CMD ["python", "/midgard/backend/main.py"]