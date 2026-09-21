# THIS SCRIPT IS MEANT TO BE EXECUTED ON A HOST MACHINE, WHERE APPARMOR IS NOT CAUSING ISSUES FOR DOCKER (e.g., on a Windows machine)

# SUGGESTED BY COPILOT
HOST_LOG_DIR="${HOST_LOG_DIR:-$HOME/honey-llm-logs}"
CONTAINER_LOG_DIR="${CONTAINER_LOG_DIR:-/app/logs}"
USE_HOST_NETWORK="${USE_HOST_NETWORK:-0}"

# ensure the host log folder exists so it can be bind-mounted into the container
mkdir -p "$HOST_LOG_DIR"
# allow the container's non-root user to write logs without host-specific UID assumptions
chmod 0777 "$HOST_LOG_DIR"

# ensure no previous container is running before (re)building and (re)running the container
docker rm -f honey-llm 2>/dev/null || true

# build the docker image
docker build --no-cache -t honey-llm-image .
