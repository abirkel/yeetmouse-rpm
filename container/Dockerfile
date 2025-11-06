FROM fedora:latest

# Install build dependencies
RUN dnf install -y \
    kernel-devel \
    gcc \
    g++ \
    make \
    rpm-build \
    libglfw3-devel \
    mesa-libGL-devel \
    git \
    wget \
    && dnf clean all

# Set working directory
WORKDIR /build

# Copy build script
COPY build-inside.sh /build/build-inside.sh
RUN chmod +x /build/build-inside.sh

# Set entrypoint
ENTRYPOINT ["/build/build-inside.sh"]
