ARG BASE_IMAGE=fedora
ARG FEDORA_VERSION=latest
FROM ${BASE_IMAGE}:${FEDORA_VERSION}

# Install build dependencies
RUN dnf install -y \
    kernel-devel \
    gcc \
    g++ \
    make \
    rpm-build \
    glfw-devel \
    mesa-libGL-devel \
    git \
    wget \
    akmods \
    && dnf clean all

# Set working directory
WORKDIR /build

# Copy build script
COPY build-inside.sh /build/build-inside.sh
RUN chmod +x /build/build-inside.sh

# Set entrypoint
ENTRYPOINT ["/build/build-inside.sh"]
