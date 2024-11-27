#! /usr/bin/env bash

# Let the DB start
python backend_pre_start.py

# Run migrations 
alembic revision --autogenerate -m "Add meta_summary to Content"

# Migrate
alembic -c alembic.ini upgrade head