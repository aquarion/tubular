FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application package
COPY tubular/ /app/tubular/

# Create directory for logs and state
RUN mkdir -p /app/data

# Run as non-root user
RUN useradd -m -u 1000 tubular && \
    chown -R tubular:tubular /app
USER tubular

CMD ["python", "-u", "-m", "tubular"]
