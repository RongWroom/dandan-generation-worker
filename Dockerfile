FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY handler.py .

# DIAGNOSTIC COMMAND: List all installed packages and then exit.
CMD ["sh", "-c", "echo '--- INSTALLED PACKAGES ---' && pip list && echo '--- END ---'"]