#!/bin/bash

# Run the version increment script
bash autoincr.sh

# Remove existing distribution files
sudo rm -rf dist/*

# Build the package
python -m build

# Add changes to git
git add .

# Commit changes with a message
git commit -m "Updating package"

# Create a new tag for the version
# Assuming autoincr.sh updates the version in a file like setup.cfg or pyproject.toml
VERSION=$(grep -Po '(?<=version = ")[^"]*' setup.cfg)  # Adjust the file path as needed
git tag "v$VERSION"

# Push changes and tags to the remote repository
git push
git push origin "v$VERSION"