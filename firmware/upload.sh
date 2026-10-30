#!/bin/bash

project=$1

if [ -z "$project" ]; then
    echo "Error: Unspecified project."
    return 1
fi

arduino-cli upload -p /dev/ttyUSB0 --fqbn esp32:esp32:esp32doit-devkit-v1 $project