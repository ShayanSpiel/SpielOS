# SpielOS Docker image
#
# Installs the published `spielos` Python package from PyPI and exposes its
# `spielos` console script as the image entrypoint. The CLI is the same
# `python3 -m company` surface used everywhere else.

FROM python:3.12-slim

LABEL org.opencontainers.image.title="spielos" \
      org.opencontainers.image.description="SpielOS AI company operating system CLI" \
      org.opencontainers.image.source="https://github.com/ShayanSpiel/SpielOS" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="6.3.0"

# Install the published package (pinned major.minor for reproducible images).
RUN pip install --no-cache-dir "spielos==6.3.0"

ENTRYPOINT ["spielos"]
CMD ["--help"]
