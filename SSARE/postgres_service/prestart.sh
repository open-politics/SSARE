#! /usr/bin/env bash

# Let the DB start
python backend_pre_start.py

# Run migrations 
# alembic revision --autogenerate -m "Initial migration"

alembic -c alembic.ini upgrade head