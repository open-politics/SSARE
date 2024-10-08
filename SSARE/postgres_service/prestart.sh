#! /usr/bin/env bash

# Let the DB start
python postgres_service/backend_pre_start.py

# Run migrations 
alembic -c postgres_service/alembic.ini upgrade head


