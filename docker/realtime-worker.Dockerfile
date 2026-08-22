# syntax=docker/dockerfile:1.7
FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04

ARG LIVEPORTRAIT_COMMIT=9b294b3d0536135442ea73cb01e6cb3ca7029dd3
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/app:/opt/LivePortrait

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip git ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/KlingAIResearch/LivePortrait.git /opt/LivePortrait \
    && cd /opt/LivePortrait \
    && git checkout "$LIVEPORTRAIT_COMMIT" \
    && rm -rf .git

RUN python3 -m pip install --no-cache-dir \
    torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cu128 \
    && python3 -m pip install --no-cache-dir \
    -r /opt/LivePortrait/requirements.txt huggingface-hub

RUN --mount=type=secret,id=HF_TOKEN \
    HF_TOKEN="$(cat /run/secrets/HF_TOKEN)" huggingface-cli download KlingTeam/LivePortrait \
    --local-dir /opt/LivePortrait/pretrained_weights \
    --exclude "*.git*" "README.md" "docs"

WORKDIR /opt/app
COPY realtime_worker/requirements.txt /tmp/realtime-requirements.txt
RUN python3 -m pip install --no-cache-dir -r /tmp/realtime-requirements.txt
COPY realtime_worker ./realtime_worker

RUN useradd -m -u 10001 worker && chown -R worker:worker /opt/app
USER worker
EXPOSE 8081
CMD ["python3", "-m", "realtime_worker.main", "start"]
