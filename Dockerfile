# Version 1.2 - Forcing correct CMD and cache invalidation
FROM python:3.10

# Install essential system-level dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install PyTorch with CUDA support first
RUN pip install torch==2.3.1 --index-url https://download.pytorch.org/whl/cu121

# Copy and install the rest of the application requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY handler.py .

# THIS IS THE CRITICAL FIX:
# Use the explicit command to start the RunPod worker module.
CMD ["python", "-u", "-m", "runpod.serverless.start", "--handler_file", "handler.py", "--handler_name", "handler"]