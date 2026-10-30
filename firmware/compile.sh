#!/bin/bash

project=$1

if [ -z "$project" ]; then
    echo "Error: Unspecified project (e.g. ./compile.sh ModuloCrecimiento)."
    exit 1
fi

arduino-cli compile --fqbn esp32:esp32:esp32doit-devkit-v1 "$project"