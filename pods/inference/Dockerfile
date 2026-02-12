FROM nvcr.io/nvidia/tritonserver:23.10-py3

LABEL maintainer="your.email@example.com"
LABEL description="Pod 4: Inference Service using Triton for NVIDIA Fraud Detection Pipeline"

# Set working directory
WORKDIR /workspace

# Install additional Python dependencies for custom backends
RUN pip install --no-cache-dir \
    requests==2.31.0 \
    numpy==1.26.3 \
    polars>=0.20.0 \
    psutil

# Copy configuration files
COPY queue_interface.py config_contract.py ./
COPY pods/inference/client.py ./

# Set environment variables
# Set default environment variables (overridden by K8s)
ENV MODEL_REPOSITORY=/mnt/cpu-fb/models
ENV PYTHONUNBUFFERED=1
ENV CUDA_VISIBLE_DEVICES=0,1

# Expose Triton ports
EXPOSE 8000 8001 8002

# Start Triton Inference Server
CMD ["sh", "-c", "tritonserver --model-repository=${MODEL_REPOSITORY} --strict-model-config=false --log-verbose=1"]
