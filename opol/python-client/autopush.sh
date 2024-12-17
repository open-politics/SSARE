#!/bin/bash

bash autoincr.sh && \
sudo rm -rf dist/* && \
python -m build && \
git add . && \
git commit -m "Updating package" && \
git push
