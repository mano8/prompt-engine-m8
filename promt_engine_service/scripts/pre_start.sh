#!/bin/sh
set -e
set -x

export PYTHONPATH=/opt/promt_engine_service

echo "Current working directory: $(pwd)"

echo "Initialysing DB..."
python -m promt_engine_service.fastapi_pre_start || { echo "Failed to initialise DB"; exit 1; }

echo "Run Migrations"
alembic -c /opt/promt_engine_service/alembic.ini upgrade head || { echo "Migration failed"; exit 1; }

# Create initial data in DB
# echo "Create initial data in DB"
# python -m promt_engine_service.initial_data || { echo "Failed to create initial data"; exit 1; }