#!/bin/bash

# Run the version increment script
bash autoincr.sh

# Remove existing distribution files
sudo rm -rf dist/*

# Build the package
python3 -m build  # Use python3 if python is not available

# Add changes to git
git add .

# Commit changes with a message
git commit -m "Updating package"

# Extract version from setup.cfg or pyproject.toml
if grep -q 'version =' setup.cfg; then
    VERSION=$(grep -Po '(?<=version = ")[^"]*' setup.cfg)
elif grep -q 'version =' pyproject.toml; then
    VERSION=$(grep -Po '(?<=version = ")[^"]*' pyproject.toml)
else
    echo "Version not found in setup.cfg or pyproject.toml"
    exit 1
fi

# Check if the tag already exists
if git rev-parse "v$VERSION" >/dev/null 2>&1; then
    echo "Tag v$VERSION already exists. Please update the version."
    exit 1
fi

git tag "v$VERSION"  # Ensure the tag includes the version number

# Push changes and tags to the remote repository
git push
git push origin "v$VERSION"