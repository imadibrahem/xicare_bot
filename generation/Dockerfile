FROM python:3.12-alpine

RUN apk add --no-cache \
    libgcc

WORKDIR /app/generation

# Install other dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt