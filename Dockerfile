FROM python:3.14-slim

# Set workdir
WORKDIR /app

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system deps (if any) and pip requirements
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . /app

# Create a non-root user and switch to it
RUN groupadd --system app && useradd --system --create-home --gid app app
USER app

EXPOSE 5000

# Default command: run waitress serving the WSGI app defined in app.py
CMD ["waitress-serve", "--host=0.0.0.0", "--port=5000", "app:app"]
