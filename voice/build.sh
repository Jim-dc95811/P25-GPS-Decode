#!/bin/sh
# Build the IMBE decoder: vendored mbelib (ISC) + our driver. No cmake needed.
cd "$(dirname "$0")"
gcc -O2 -I mbelib mbelib/*.c imbe_dec.c -lm -o imbe_dec && echo "built: $(pwd)/imbe_dec"
