FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY handler.py .

CMD ["python", "-u", "-m", "runpod.serverless.start", "--handler_file", "handler.py", "--handler_name", "handler"]
