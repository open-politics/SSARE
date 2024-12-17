#! /usr/bin/env bash

# Let the DB start
python backend_pre_start.py

# Run migrations 
# alembic revision --autogenerate -m "Adding top locations and entities to content"

# # Migrate
alembic upgrade head