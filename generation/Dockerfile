FROM python:3.12-alpine

# Install required system packages
RUN apk add --no-cache \
    libgcc \
    curl

WORKDIR /app/generation

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your actual app code
COPY . .

