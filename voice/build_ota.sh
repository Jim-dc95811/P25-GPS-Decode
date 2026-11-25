#!/bin/sh
# Build the OTA IMBE voice decoder (vendored mbelib + imbe_ota driver).
cd "$(dirname "$0")"
gcc -O2 -I mbelib mbelib/*.c imbe_ota.c -lm -o imbe_ota && echo "built: $(pwd)/imbe_ota"
