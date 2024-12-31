#!/bin/bash

# Run the tests
pytest tests/api.py


uvicorn main:app --host 0.0.0.0 --port 8089 --reload