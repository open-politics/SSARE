#!/bin/bash

# Function to increment version
increment_version() {
  local version=$1
  local delimiter=.
  local array=($(echo "$version" | tr $delimiter '\n'))
  array[2]=$((array[2]+1))
  echo "${array[0]}.${array[1]}.${array[2]}"
}

# Get current version from setup.cfg
current_version=$(grep -oP '(?<=version = )\d+\.\d+\.\d+' setup.cfg)

# Increment the version
new_version=$(increment_version $current_version)

# Update setup.cfg
sed -i "s/version = $current_version/version = $new_version/" setup.cfg

# Update pyproject.toml
sed -i "s/version = \"$current_version\"/version = \"$new_version\"/" pyproject.toml

echo "Version updated to $new_version"