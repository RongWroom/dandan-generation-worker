FROM runpod/pytorch:2.2.2-py3.10-cuda12.1.1-devel

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY handler.py .

CMD ["python", "-u", "-m", "runpod.serverless.start", "--handler_file", "handler.py", "--handler_name", "handler"]