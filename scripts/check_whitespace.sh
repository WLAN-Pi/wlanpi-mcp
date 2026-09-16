#!/bin/bash
# Fail if any Python source file has trailing whitespace.
status=0
while IFS= read -r -d '' file; do
    if ! sed 's/[[:space:]]*$//' "$file" | cat -A | diff --color=always - <(cat -A "$file"); then
        echo "trailing whitespace: $file" >&2
        status=1
    fi
done < <(find wlanpi_mcp -type f -name "*.py" -print0)
exit $status
