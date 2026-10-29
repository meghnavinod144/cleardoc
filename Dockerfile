# Dockerfile — the recipe for ClearDoc's shipping container.
#
# GENERAL IDEA (not just this project): "works on my machine" dies here.
# A container packs the app + its exact dependencies + the OS pieces it
# needs into one sealed, portable box. The same box runs identically on
# a laptop, a colleague's machine, or any cloud — Azure just runs boxes.
# Docker reads this file top to bottom and builds the box in layers;
# unchanged layers are cached, so rebuilds are fast.

# Layer 1: the base — a minimal Linux with Python preinstalled.
FROM python:3.12-slim

# Layer 2: system tools our pipeline needs (same ones CI installs).
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/cleardoc

# Layer 3: Python dependencies — copied ALONE first, on purpose:
# code changes daily, requirements rarely. This ordering means a code
# change doesn't re-download every library (layer caching at work).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Layer 4: the application code.
COPY app/ app/
RUN mkdir -p data/uploads

# Containers get configuration from ENVIRONMENT VARIABLES, never from
# baked-in files: the same image runs in dev and prod with different
# settings (API keys, DB URL) injected at start time.
ENV PYTHONUNBUFFERED=1

# Document which door the app listens on.
EXPOSE 8000

# What runs when the box starts.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
