FROM python:3.11-slim

# Install tectonic for LaTeX compilation
RUN apt-get update && apt-get install -y \
    tectonic \
    ghostscript \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 7860
CMD ["python3", "app.py"]
