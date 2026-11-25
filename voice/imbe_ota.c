/* imbe_ota.c - decode OTA P25 IMBE voice frames to PCM via mbelib.
 *
 * Reads a stream of deinterleaved IMBE frames from a file: each frame is
 * 8*23 = 184 bytes, value 0/1, laid out as imbe_fr[8][23] row-major
 * (the 8 code vectors c0..c7; widths 23,23,23,23,15,15,15,7 - unused
 * cells are 0). mbelib does C0 Golay, PN descramble, Golay/Hamming ECC,
 * and IMBE synthesis internally (mbe_processImbe7200x4400Frame).
 *
 * Writes signed 16-bit mono PCM at 8000 Hz to stdout (160 samples/frame).
 *
 * Build: see build_ota.sh. Usage: imbe_ota <frames.bin> > out.s16
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "mbelib/mbelib.h"

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: %s <frames.bin>\n", argv[0]); return 1; }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror("open"); return 1; }

    mbe_parms cur, prev, penh;
    mbe_initMbeParms(&cur, &prev, &penh);

    char imbe_fr[8][23];
    char imbe_d[88];
    short aout[160];
    int errs = 0, errs2 = 0;
    char errstr[64];
    unsigned char buf[8 * 23];
    long nframes = 0;

    while (fread(buf, 1, sizeof(buf), f) == sizeof(buf)) {
        for (int r = 0; r < 8; r++)
            for (int c = 0; c < 23; c++)
                imbe_fr[r][c] = (char)(buf[r * 23 + c] & 1);

        mbe_processImbe7200x4400Frame(aout, &errs, &errs2, errstr,
                                      imbe_fr, imbe_d, &cur, &prev, &penh, 3);
        fwrite(aout, sizeof(short), 160, stdout);
        nframes++;
    }
    fclose(f);
    fprintf(stderr, "decoded %ld IMBE frames -> %ld PCM samples (%.2f s @8kHz)\n",
            nframes, nframes * 160L, nframes * 160.0 / 8000.0);
    return 0;
}
