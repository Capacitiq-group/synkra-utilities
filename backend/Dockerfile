FROM python:3.12-slim

# libmagic is required by python-magic for real content-type detection.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-fetch the rembg (U2Net) model at build time so the first real
# request doesn't pay for a ~176MB cold-start download.
RUN python -c "from rembg import new_session; new_session('u2net')"

COPY app ./app

ENV SYNKRA_TEMP_DIR=/tmp/synkra-utilities
RUN mkdir -p /tmp/synkra-utilities

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
