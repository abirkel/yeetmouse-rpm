#!/bin/bash

# YeetMouse RPM Builder - Main Build Script
# This script orchestrates the containerized build process for YeetMouse RPM packages

set -euo pipefail

# Default configuration
FEDORA_VERSION="40"
OUTPUT_DIR="./build-output"
SKIP_KMOD=false
SKIP_AKMOD=false
KEEP_CONTAINER=false
CONTAINER_RUNTIME=""
CONTAINER_NAME="yeetmouse-rpm-builder"
BUILD_LOG="${OUTPUT_DIR}/build.log"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored messages
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1" | tee -a "${BUILD_LOG}"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "${BUILD_LOG}"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "${BUILD_LOG}"
}

log_progress() {
    echo -e "${BLUE}[PROGRESS]${NC} $1" | tee -a "${BUILD_LOG}"
}

# Function to display help message
show_help() {
    cat << EOF
YeetMouse RPM Builder

Usage: ./build.sh [OPTIONS]

Options:
  --fedora-version VERSION    Fedora version to use for build (default: 40)
  --output-dir PATH           Output directory for RPM files (default: ./build-output)
  --skip-kmod                 Skip building kmod package
  --skip-akmod                Skip building akmod package
  --keep-container            Keep container after build completes
  --help                      Show this help message

Examples:
  ./build.sh
  ./build.sh --fedora-version 41 --output-dir /tmp/rpms
  ./build.sh --skip-kmod --keep-container

EOF
}

# Function to check for docker or podman
check_container_runtime() {
    log_progress "Checking for container runtime..."
    
    if command -v docker &> /dev/null; then
        CONTAINER_RUNTIME="docker"
        log_info "Found Docker"
        return 0
    elif command -v podman &> /dev/null; then
        CONTAINER_RUNTIME="podman"
        log_info "Found Podman"
        return 0
    else
        log_error "Neither Docker nor Podman found. Please install one of them."
        log_error "Docker: https://docs.docker.com/get-docker/"
        log_error "Podman: https://podman.io/getting-started/installation"
        exit 1
    fi
}

# Function to validate output directory
validate_output_dir() {
    log_progress "Validating output directory: ${OUTPUT_DIR}"
    
    # Create output directory if it doesn't exist
    if [[ ! -d "${OUTPUT_DIR}" ]]; then
        log_info "Creating output directory..."
        mkdir -p "${OUTPUT_DIR}" || {
            log_error "Failed to create output directory: ${OUTPUT_DIR}"
            exit 2
        }
    fi
    
    # Check if directory is writable
    if [[ ! -w "${OUTPUT_DIR}" ]]; then
        log_error "Output directory is not writable: ${OUTPUT_DIR}"
        exit 2
    fi
    
    # Convert to absolute path
    OUTPUT_DIR=$(cd "${OUTPUT_DIR}" && pwd)
    BUILD_LOG="${OUTPUT_DIR}/build.log"
    
    log_info "Output directory validated: ${OUTPUT_DIR}"
}

# Function to build container image
build_container_image() {
    log_progress "Building container image..."
    
    local image_tag="${CONTAINER_NAME}:fedora${FEDORA_VERSION}"
    local image_build_log="${OUTPUT_DIR}/image-build.log"
    
    log_info "Container image tag: ${image_tag}"
    log_info "Image build output will be logged to: ${image_build_log}"
    
    ${CONTAINER_RUNTIME} build \
        --build-arg FEDORA_VERSION="${FEDORA_VERSION}" \
        -t "${image_tag}" \
        -f container/Dockerfile \
        container/ 2>&1 | tee -a "${BUILD_LOG}" "${image_build_log}"
    
    if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
        log_error "Container image build failed"
        log_error "See ${image_build_log} for details"
        exit 3
    fi
    
    log_info "Container image built successfully: ${image_tag}"
    echo "${image_tag}"
}

# Function to run build inside container
run_container_build() {
    local image_tag=$1
    local container_id
    local container_log="${OUTPUT_DIR}/container-build.log"
    
    log_progress "Starting container build process..."
    log_info "Build options: SKIP_KMOD=${SKIP_KMOD}, SKIP_AKMOD=${SKIP_AKMOD}"
    
    # Prepare environment variables for container
    local env_args=()
    if [[ "${SKIP_KMOD}" == "true" ]]; then
        env_args+=(-e SKIP_KMOD=1)
    fi
    if [[ "${SKIP_AKMOD}" == "true" ]]; then
        env_args+=(-e SKIP_AKMOD=1)
    fi
    
    # Generate unique container ID
    container_id="${CONTAINER_NAME}-$(date +%s)"
    
    log_info "Container ID: ${container_id}"
    log_info "Container output will be logged to: ${container_log}"
    log_info "=========================================="
    log_progress "Container build output:"
    log_info "=========================================="
    
    # Run container with volume mount
    ${CONTAINER_RUNTIME} run \
        --name "${container_id}" \
        -v "${OUTPUT_DIR}:/output:Z" \
        "${env_args[@]}" \
        "${image_tag}" 2>&1 | tee -a "${BUILD_LOG}" "${container_log}"
    
    local exit_code=${PIPESTATUS[0]}
    
    log_info "=========================================="
    
    if [[ ${exit_code} -ne 0 ]]; then
        log_error "Container build process failed with exit code ${exit_code}"
        log_error "Container output saved to: ${container_log}"
        log_error "Review the container log for detailed error information"
        cleanup_container "${container_id}"
        exit 4
    fi
    
    log_info "Container build completed successfully"
    log_info "Container output saved to: ${container_log}"
    
    # Cleanup container unless --keep-container is specified
    if [[ "${KEEP_CONTAINER}" == "false" ]]; then
        cleanup_container "${container_id}"
    else
        log_info "Container kept as requested: ${container_id}"
    fi
}

# Function to cleanup container
cleanup_container() {
    local container_id=$1
    
    log_progress "Cleaning up container: ${container_id}"
    
    ${CONTAINER_RUNTIME} rm -f "${container_id}" &> /dev/null || true
    
    log_info "Container cleanup complete"
}

# Function to report build results
report_results() {
    log_info "=========================================="
    log_info "Build completed successfully!"
    log_info "=========================================="
    log_info ""
    log_info "Build Summary:"
    log_info "  Output directory: ${OUTPUT_DIR}"
    log_info "  Build log: ${BUILD_LOG}"
    log_info ""
    
    # List all generated files
    local rpm_count=0
    local spec_count=0
    local log_count=0
    
    log_info "Generated files:"
    
    # Count and list RPM files
    if compgen -G "${OUTPUT_DIR}/*.rpm" > /dev/null; then
        for rpm in "${OUTPUT_DIR}"/*.rpm; do
            log_info "  [RPM] $(basename "${rpm}")"
            ((rpm_count++))
        done
    fi
    
    # Count and list spec files
    if compgen -G "${OUTPUT_DIR}/*.spec" > /dev/null; then
        for spec in "${OUTPUT_DIR}"/*.spec; do
            log_info "  [SPEC] $(basename "${spec}")"
            ((spec_count++))
        done
    fi
    
    # Count and list log files
    if compgen -G "${OUTPUT_DIR}/*.log" > /dev/null; then
        for log_file in "${OUTPUT_DIR}"/*.log; do
            log_info "  [LOG] $(basename "${log_file}")"
            ((log_count++))
        done
    fi
    
    # List metadata file if present
    if [[ -f "${OUTPUT_DIR}/build-metadata.txt" ]]; then
        log_info "  [METADATA] build-metadata.txt"
    fi
    
    log_info ""
    log_info "Summary:"
    log_info "  RPM packages: ${rpm_count}"
    log_info "  Spec files: ${spec_count}"
    log_info "  Log files: ${log_count}"
    log_info ""
    
    # Display build metadata if available
    if [[ -f "${OUTPUT_DIR}/build-metadata.txt" ]]; then
        log_info "Build Metadata:"
        while IFS= read -r line; do
            log_info "  $line"
        done < "${OUTPUT_DIR}/build-metadata.txt"
    fi
}

# Parse command-line arguments
parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --fedora-version)
                FEDORA_VERSION="$2"
                shift 2
                ;;
            --output-dir)
                OUTPUT_DIR="$2"
                shift 2
                ;;
            --skip-kmod)
                SKIP_KMOD=true
                shift
                ;;
            --skip-akmod)
                SKIP_AKMOD=true
                shift
                ;;
            --keep-container)
                KEEP_CONTAINER=true
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

# Main execution
main() {
    echo "YeetMouse RPM Builder"
    echo "===================="
    echo ""
    
    # Parse arguments
    parse_arguments "$@"
    
    # Initialize build log
    mkdir -p "$(dirname "${BUILD_LOG}")" 2>/dev/null || true
    {
        echo "=========================================="
        echo "Build started at $(date)"
        echo "=========================================="
    } > "${BUILD_LOG}"
    
    log_info "Fedora version: ${FEDORA_VERSION}"
    log_info "Output directory: ${OUTPUT_DIR}"
    log_info ""
    
    # Validate prerequisites
    check_container_runtime
    validate_output_dir
    
    # Build and run
    local image_tag
    image_tag=$(build_container_image)
    run_container_build "${image_tag}"
    
    # Report results
    report_results
    
    log_progress "Build process complete!"
    log_info "=========================================="
}

# Run main function with all arguments
main "$@"
