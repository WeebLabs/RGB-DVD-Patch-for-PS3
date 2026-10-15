# Cell SDK build environment (the SDK itself is not included)
# Uses Wine to run the Windows Cell SDK toolchain on Linux.

FROM --platform=linux/amd64 ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

# Enable 32-bit architecture (required by Wine and some SDK tools)
RUN dpkg --add-architecture i386 && \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    wine64 \
    wine32 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf "$(which wine64-stable || which wine64 || which wine)" /usr/local/bin/wine

# Suppress Wine debug noise
ENV WINEDEBUG=-all

# Cell SDK location inside the container
ENV CELL_SDK=/opt/cell
ENV WINE=wine

WORKDIR /src
