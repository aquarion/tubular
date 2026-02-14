#!/bin/bash
set -e

RANDOM_SUFFIX=$(head /dev/urandom | tr -dc a-z0-9 | head -c 6)
CONTAINER_NAME="tubular-run-${RANDOM_SUFFIX}"

docker build --file Dockerfile.dev -t "${CONTAINER_NAME}" .
docker run --rm --env-file .env -v ./src:/app/tubular "${CONTAINER_NAME}" python -m tubular && RETURN_CODE=0 || RETURN_CODE=$?
docker image rm "${CONTAINER_NAME}"

exit "$RETURN_CODE"
