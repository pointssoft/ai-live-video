FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PYTHONPATH=/opt/mimicmotion \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 WORKSPACE_ROOT=/tmp/mimicmotion
RUN apt-get update && apt-get install -y --no-install-recommends python3.11 python3-pip ffmpeg libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/mimicmotion
COPY worker/requirements.txt /tmp/worker-requirements.txt
RUN python3.11 -m pip install --no-cache-dir -r /tmp/worker-requirements.txt \
    torch==2.3.1 torchvision==0.18.1 diffusers==0.29.2 transformers==4.42.4 \
    accelerate==0.31.0 opencv-python-headless==4.10.0.84 \
    av==12.2.0 decord==0.6.0 matplotlib==3.9.1 einops==0.8.0 numpy==1.26.4 pillow==10.4.0 tqdm==4.66.4
RUN python3.11 -m pip install --no-cache-dir --index-url \
    https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-12/pypi/simple/ \
    onnxruntime-gpu==1.18.1
RUN python3.11 -m pip install --no-cache-dir --no-deps --target /opt/cudnn9 \
    nvidia-cudnn-cu12==9.1.0.70
ENV LD_LIBRARY_PATH=/opt/cudnn9/nvidia/cudnn/lib:/usr/local/nvidia/lib:/usr/local/nvidia/lib64
RUN python3.11 -c "import onnxruntime as ort; assert 'CUDAExecutionProvider' in ort.get_available_providers(); print(ort.__version__, ort.get_available_providers())" \
    && ! ldd /usr/local/lib/python3.11/dist-packages/onnxruntime/capi/libonnxruntime_providers_cuda.so | grep "not found"
COPY constants.py inference.py ./
COPY mimicmotion ./mimicmotion
COPY worker ./worker
RUN useradd -m -u 10001 worker \
    && mkdir -p /tmp/mimicmotion \
    && chown -R worker:worker /tmp/mimicmotion \
    && touch /opt/mimicmotion/.runpod_jobs.pkl /opt/mimicmotion/.runpod_jobs.pkl.lock \
    && chown worker:worker /opt/mimicmotion \
        /opt/mimicmotion/.runpod_jobs.pkl /opt/mimicmotion/.runpod_jobs.pkl.lock
USER worker
CMD ["python3.11", "-m", "worker.handler"]
