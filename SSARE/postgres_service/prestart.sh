#! /usr/bin/env bash

# Let the DB start
python backend_pre_start.py

# Run migrations 
# alembic revision --autogenerate -m "Add unique constraint to classificationdimension.name"

alembic -c alembic.ini upgrade head




