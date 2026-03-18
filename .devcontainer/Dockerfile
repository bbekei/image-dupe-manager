FROM mcr.microsoft.com/devcontainers/python:3.11

# Tauri system dependencies (Linux)
RUN apt-get update && apt-get install -y \
    libwebkit2gtk-4.1-dev \
    build-essential \
    curl \
    wget \
    file \
    libssl-dev \
    libayatana-appindicator3-dev \
    librsvg2-dev \
    libgtk-3-dev \
    libxdo-dev \
    pkg-config \
    gcc-mingw-w64-x86-64 \
    g++-mingw-w64-x86-64 \
    binutils-mingw-w64-x86-64 \
    nsis \
    && rm -rf /var/lib/apt/lists/*
