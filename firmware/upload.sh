#!/bin/bash

project=$1
port=${2:-/dev/ttyUSB0}

if [ -z "$project" ]; then
    echo "Error: Unspecified project (e.g. ./upload.sh ModuloCrecimiento /dev/ttyUSB0)."
    exit 1
fi

arduino-cli upload -p "$port" --fqbn esp32:esp32:esp32doit-devkit-v1 "$project"