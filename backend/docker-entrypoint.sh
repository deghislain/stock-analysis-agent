#!/bin/sh
# docker-entrypoint.sh
#
# Run as root (via Dockerfile USER root before the ENTRYPOINT) only long
# enough to fix volume-mount ownership, then drop privileges to appuser.
#
# Named volumes created by Docker are owned by root on first initialisation.
# Without this step the non-root appuser cannot write PDFs or the SQLite DB.

set -e

# Ensure both volume mount points exist and are owned by appuser.
mkdir -p /app/pdf_reports /app/data
chown -R appuser:appgroup /app/pdf_reports /app/data

# Drop to non-root and exec the real process, replacing this shell.
exec gosu appuser "$@"
