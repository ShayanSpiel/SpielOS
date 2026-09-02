# SpielOS Docker image
#
# Installs the published `spielos` Python package from PyPI and exposes its
# `spielos` console script as the image entrypoint. The publish workflows
# pass SPIELOS_VERSION as a build arg so this file never drifts.

FROM python:3.12-slim

ARG SPIELOS_VERSION=10.0.2

LABEL org.opencontainers.image.title="spielos" \
      org.opencontainers.image.description="SpielOS AI company operating system CLI" \
      org.opencontainers.image.source="https://github.com/ShayanSpiel/SpielOS" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${SPIELOS_VERSION}"

# The index can lag the publish by a few seconds; retry briefly.
RUN attempt=1; until pip install --no-cache-dir "spielos==${SPIELOS_VERSION}"; do \
      attempt=$((attempt+1)); \
      if [ "$attempt" -gt 6 ]; then exit 1; fi; \
      echo "waiting for PyPI to list spielos ${SPIELOS_VERSION}..."; sleep 20; \
    done

ENTRYPOINT ["spielos"]
CMD ["--help"]
