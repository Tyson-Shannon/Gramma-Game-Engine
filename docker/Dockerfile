# Pinned Gramma toolchain images. Build one stage at a time:
#   docker build -f docker/Dockerfile --target gbdk -t gramma/gbdk:4.6.0 .
#   docker build -f docker/Dockerfile --target cc65 -t gramma/cc65:2.19 .
#   docker build -f docker/Dockerfile --target sms -t gramma/sms:4.5.0 .
#   docker build -f docker/Dockerfile --target dev -t gramma/dev:latest .
#
# The same values are used by ./tools/gr/gr and .github/workflows/ci.yml where
# possible. Checksums make each download reproducible, not just version-pinned.

ARG UBUNTU_VERSION=24.04

FROM ubuntu:${UBUNTU_VERSION} AS base
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl tar bzip2 xz-utils \
 && rm -rf /var/lib/apt/lists/*

# --- GBDK-2020 ------------------------------------------------------------

FROM base AS gbdk
ARG GBDK_VERSION=4.6.0
ARG GBDK_SHA256=c033dac026b99c080f07c2a659eb25976f65ca114cb15d1570bbb23c99c27e35
RUN curl -fsSL \
      "https://github.com/gbdk-2020/gbdk-2020/releases/download/${GBDK_VERSION}/gbdk-linux64.tar.gz" \
      -o /tmp/gbdk.tgz \
 && echo "${GBDK_SHA256}  /tmp/gbdk.tgz" | sha256sum -c - \
 && tar -xzf /tmp/gbdk.tgz -C /opt \
 && rm /tmp/gbdk.tgz
ENV GBDK_HOME=/opt/gbdk
ENV PATH=/opt/gbdk/bin:$PATH

# --- cc65 ----------------------------------------------------------------

FROM base AS cc65
ARG CC65_VERSION=2.19
ARG CC65_SHA256=157b8051aed7f534e5093471e734e7a95e509c577324099c3c81324ed9d0de77
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential make \
 && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL \
      "https://github.com/cc65/cc65/archive/refs/tags/V${CC65_VERSION}.tar.gz" \
      -o /tmp/cc65.tgz \
 && echo "${CC65_SHA256}  /tmp/cc65.tgz" | sha256sum -c - \
 && tar -xzf /tmp/cc65.tgz -C /tmp \
 && make -C "/tmp/cc65-${CC65_VERSION}" -j"$(nproc)" \
 && make -C "/tmp/cc65-${CC65_VERSION}" PREFIX=/opt/cc65 install \
 && rm -rf /tmp/cc65.tgz "/tmp/cc65-${CC65_VERSION}"
ENV CC65_HOME=/opt/cc65
ENV PATH=/opt/cc65/bin:$PATH

# --- SDCC 4.5.0 + pinned devkitSMS ----------------------------------------

FROM base AS sms
ARG SDCC_VERSION=4.5.0
ARG SDCC_SHA256=d5030437fb436bb1d93a8dbdbfb46baaa60613318f4fb3f5871d72815d1eed80
ARG DEVKITSMS_COMMIT=561bc2cb9829cdf2e31ad8cd43835037c8c44a63
ARG DEVKITSMS_SHA256=221efd6b136925f8310cb4504a5e3376f11e3bff2a26d3fcc616871794885b55
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential bison flex libboost-dev make \
 && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL \
      "https://downloads.sourceforge.net/project/sdcc/sdcc/${SDCC_VERSION}/sdcc-src-${SDCC_VERSION}.tar.bz2" \
      -o /tmp/sdcc.tar.bz2 \
 && echo "${SDCC_SHA256}  /tmp/sdcc.tar.bz2" | sha256sum -c - \
 && tar -xjf /tmp/sdcc.tar.bz2 -C /tmp \
 && cd "/tmp/sdcc-${SDCC_VERSION}" \
 && ./configure --prefix=/opt/sdcc \
 && make -j"$(nproc)" \
 && make install \
 && cd / \
 && rm -rf /tmp/sdcc.tar.bz2 "/tmp/sdcc-${SDCC_VERSION}"
RUN curl -fsSL \
      "https://github.com/sverx/devkitSMS/archive/${DEVKITSMS_COMMIT}.tar.gz" \
      -o /tmp/devkitsms.tgz \
 && echo "${DEVKITSMS_SHA256}  /tmp/devkitsms.tgz" | sha256sum -c - \
 && mkdir -p /opt/devkitsms \
 && tar -xzf /tmp/devkitsms.tgz -C /opt/devkitsms --strip-components=1 \
 && rm /tmp/devkitsms.tgz
ENV SDCC_HOME=/opt/sdcc
ENV DEVKITSMS_HOME=/opt/devkitsms
ENV PATH=/opt/sdcc/bin:$PATH

# --- All host and console tools in one image ------------------------------

FROM base AS dev
COPY --from=gbdk /opt/gbdk /opt/gbdk
COPY --from=cc65 /opt/cc65 /opt/cc65
COPY --from=sms /opt/sdcc /opt/sdcc
COPY --from=sms /opt/devkitsms /opt/devkitsms
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential git libsdl2-dev meson ninja-build nodejs pkg-config \
      python3 python3-pip python3-venv \
 && python3 -m pip install --no-cache-dir pillow numpy pyboy 'nes-py>=9' \
 && rm -rf /var/lib/apt/lists/*
ENV GBDK_HOME=/opt/gbdk
ENV CC65_HOME=/opt/cc65
ENV SDCC_HOME=/opt/sdcc
ENV DEVKITSMS_HOME=/opt/devkitsms
ENV PATH=/opt/gbdk/bin:/opt/cc65/bin:/opt/sdcc/bin:$PATH
ENV GRAMMA_TOOLCHAINS="gbdk 4.6.0; cc65 2.19; sdcc 4.5.0; devkitSMS 561bc2cb9829cdf2e31ad8cd43835037c8c44a63"
WORKDIR /workspace
CMD ["/bin/bash"]
