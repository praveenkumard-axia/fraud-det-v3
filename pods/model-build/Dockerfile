# Pod 3: Model Training
# XGBoost with GPU acceleration

FROM nvcr.io/nvidia/rapidsai/base:24.04-cuda12.0-py3.10

WORKDIR /app

# Copy requirements first (for better layer caching)
COPY pods/model-build/requirements.txt ./requirements.txt

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY queue_interface.py config_contract.py ./
COPY pods/ pods/

ENV PREP_OUTPUT_DIR=/data/input
ENV FA_MOUNT=/data/models
ENV FEATURES_FILE=""
ENV PYTHONUNBUFFERED=1

CMD ["python", "train.py"]