FROM python:3.11-slim

# Install tectonic (static binary, not in Debian apt) for LaTeX compilation
RUN apt-get update && apt-get install -y \
    curl \
    ghostscript \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL -o /tmp/tectonic.tar.gz https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.17.0/tectonic-0.17.0-x86_64-unknown-linux-musl.tar.gz \
    && tar -xzf /tmp/tectonic.tar.gz -C /tmp \
    && mv /tmp/tectonic /usr/local/bin/tectonic \
    && chmod +x /usr/local/bin/tectonic \
    && rm /tmp/tectonic.tar.gz \
    && tectonic --version

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python3 -m spacy download en_core_web_sm

COPY . .

EXPOSE 7860
CMD ["python3", "app.py"]
