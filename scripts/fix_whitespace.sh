#!/bin/bash
find wlanpi_mcp -type f -name "*.py" -exec sed -i 's/[[:space:]]*$//' {} +
