#!/bin/sh
set -e

# Always ensure /app/data is owned by nonroot, regardless of volume history,
# host UID, or when it was created. Idempotent — safe to run every start.
chown -R nonroot:nonroot /app/data

export HOME=/home/nonroot

# Drop from root to nonroot and exec the real command (replaces this shell,
# so nonroot's process becomes PID 1 — signals/restarts work correctly)
exec setpriv --reuid=999 --regid=999 --clear-groups "$@"