FROM malaknoyn/mimicmotion-worker:phase1

USER root
WORKDIR /opt/mimicmotion
RUN python3.11 -m pip install --no-cache-dir --no-deps --target /opt/ort-cuda12 \
    --index-url \
    https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-12/pypi/simple/ \
    onnxruntime-gpu==1.18.1
RUN python3.11 -m pip install --no-cache-dir --no-deps --target /opt/cudnn9 \
    nvidia-cudnn-cu12==9.1.0.70
ENV PYTHONPATH=/opt/ort-cuda12:/opt/mimicmotion \
    LD_LIBRARY_PATH=/opt/cudnn9/nvidia/cudnn/lib:/usr/local/nvidia/lib:/usr/local/nvidia/lib64
RUN python3.11 -m pip install --no-cache-dir "boto3>=1.35,<2"
COPY worker ./worker
RUN chown -R worker:worker /opt/mimicmotion/worker
USER worker

ENV WORKER_MODE=model-smoke
CMD ["python3.11", "-m", "worker.handler"]
