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

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored messages
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1" >&2
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" >&2
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_progress() {
    echo -e "${BLUE}[PROGRESS]${NC} $1" >&2
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
    OUTPUT_DIR=$(realpath "${OUTPUT_DIR}")
    
    log_info "Output directory validated: ${OUTPUT_DIR}"
}

# Function to build container image
build_container_image() {
    log_progress "Building container image..."
    
    local image_tag="${CONTAINER_NAME}:fedora${FEDORA_VERSION}"
    
    log_info "Container image tag: ${image_tag}"
    
    if ! ${CONTAINER_RUNTIME} build \
        --build-arg FEDORA_VERSION="${FEDORA_VERSION}" \
        -t "${image_tag}" \
        -f container/Dockerfile \
        container/; then
        log_error "Container image build failed"
        exit 3
    fi
    
    log_info "Container image built successfully: ${image_tag}"
    echo "${image_tag}"
}

# Function to run build inside container
run_container_build() {
    local image_tag=$1
    local container_id
    
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
    
    # Get absolute path to specs directory
    local specs_dir
    specs_dir=$(realpath "./specs")
    
    if [[ ! -d "${specs_dir}" ]]; then
        log_error "Specs directory not found: ${specs_dir}"
        exit 2
    fi
    
    # Generate unique container ID
    container_id="${CONTAINER_NAME}-$(date +%s)"
    
    log_info "Container ID: ${container_id}"
    log_info "Output directory: ${OUTPUT_DIR}"
    log_info "Specs directory: ${specs_dir}"
    log_info "=========================================="
    log_progress "Container build output:"
    log_info "=========================================="
    
    # Run container with volume mounts for output and specs
    ${CONTAINER_RUNTIME} run \
        --name "${container_id}" \
        -v "${OUTPUT_DIR}:/output" \
        -v "${specs_dir}:/specs:ro" \
        "${env_args[@]}" \
        "${image_tag}"
    
    local exit_code=$?
    
    log_info "=========================================="
    
    if [[ ${exit_code} -ne 0 ]]; then
        log_error "Container build process failed with exit code ${exit_code}"
        log_error "Check build logs in ${OUTPUT_DIR} for details"
        cleanup_container "${container_id}"
        exit 4
    fi
    
    log_info "Container build completed successfully"
    
    # Cleanup container unless --keep-container is specified
    if [[ "${KEEP_CONTAINER}" == "false" ]]; then
        cleanup_container "${container_id}"
    else
        log_info "Container kept as requested: ${container_id}"
    fi
    
    return 0
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
    log_info ""
    
    # List all generated files
    local rpm_count=0
    local spec_count=0
    local log_count=0
    
    log_info "Generated files:"
    
    # Count and list RPM files using find to ensure we get all files
    while IFS= read -r rpm; do
        log_info "  [RPM] $(basename "${rpm}")"
        ((rpm_count++))
    done < <(find "${OUTPUT_DIR}" -maxdepth 1 -name "*.rpm" -type f | sort)
    
    # Count and list spec files
    while IFS= read -r spec; do
        log_info "  [SPEC] $(basename "${spec}")"
        ((spec_count++))
    done < <(find "${OUTPUT_DIR}" -maxdepth 1 -name "*.spec" -type f | sort)
    
    # Count and list log files
    while IFS= read -r logfile; do
        log_info "  [LOG] $(basename "${logfile}")"
        ((log_count++))
    done < <(find "${OUTPUT_DIR}" -maxdepth 1 -name "*-rpmbuild.log" -type f | sort)
    
    # List metadata file if present
    if [[ -f "${OUTPUT_DIR}/build-metadata.txt" ]]; then
        log_info "  [METADATA] build-metadata.txt"
    fi
    
    log_info ""
    log_info "Summary:"
    log_info "  RPM packages: ${rpm_count}"
    log_info "  Spec files: ${spec_count}"
    log_info "  Build logs: ${log_count}"
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
    
    log_info "Fedora version: ${FEDORA_VERSION}"
    log_info "Output directory: ${OUTPUT_DIR}"
    log_info ""
    
    # Validate prerequisites
    check_container_runtime
    validate_output_dir
    
    # Build and run
    local image_tag
    image_tag=$(build_container_image)
    
    # Run container build and check if it succeeded
    if ! run_container_build "${image_tag}"; then
        log_error "Build failed!"
        exit 1
    fi
    
    # Report results only if build succeeded
    report_results
    
    log_progress "Build process complete!"
    log_info "=========================================="
}

# Run main function with all arguments
main "$@"
