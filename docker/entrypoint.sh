#!/bin/sh
set -eu

attempt=1
max_attempts="${DATABASE_MIGRATION_ATTEMPTS:-30}"

while ! flask --app run.py db upgrade; do
    if [ "$attempt" -ge "$max_attempts" ]; then
        echo "Database migration failed after $attempt attempts." >&2
        exit 1
    fi
    echo "Database is not ready; retrying migration ($attempt/$max_attempts)..." >&2
    attempt=$((attempt + 1))
    sleep 2
done

exec "$@"
