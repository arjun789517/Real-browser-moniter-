FROM python:3.10-slim

# Install system dependencies for Chrome & Selenium
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for Chrome
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Set display port to avoid errors (headless doesn't need real display)
ENV DISPLAY=:99

# Create working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY app.py .

# Create a volume for the database (optional, to persist monitors across restarts)
VOLUME ["/app/data"]
# We'll keep DB in /app by default, but can be changed. For persistence, you can mount a volume.

# Expose Streamlit default port
EXPOSE 8501

# Healthcheck (optional) to ensure Streamlit is running
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Run Streamlit app
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.enableCORS=false", "--server.enableXsrfProtection=false"]
