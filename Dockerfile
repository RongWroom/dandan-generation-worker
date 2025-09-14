# Version 3.0 - Using the official RunPod PyTorch Template
FROM runpod/pytorch:2.2.1-py3.10-cuda11.8.0-devel

WORKDIR /app

COPY requirements.txt .
COPY handler.py .

# PyTorch is already in the base image. We just install our application's libraries.
RUN pip install --no-cache-dir -r requirements.txt

# The base image is pre-configured to start the worker correctly.
CMD ["python", "-u", "-m", "runpod.serverless.start", "--handler_file", "handler.py", "--handler_name", "handler"]