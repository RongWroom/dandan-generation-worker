# Version 2.0 - Using the full python base image for reliability
FROM python:3.10

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY handler.py .

# Use the explicit command to start the RunPod worker
CMD ["python", "-u", "-m", "runpod.serverless.start", "--handler_file", "handler.py", "--handler_name", "handler"]