"""C4FM symbol recovery (OP25 tracking_loop_mmse), STDLIB-ONLY for the box.
Float samples in -> soft 4-level symbols out. Identical loop to the numpy
fsk4_demod.py; the 129x8 MMSE interpolation table is precomputed in taps_data.py.
"""
import math
from taps_data import MMSE_TAPS as TAPS

NTAPS, NSTEPS = 8, 128
K_SYMBOL_SPREAD = 0.0100; K_SYMBOL_TIMING = 0.025
K_FINE_FREQUENCY = 0.125; K_COARSE_FREQUENCY = 0.00125
SPREAD_MAX = 2.4; SPREAD_MIN = 1.6

def fsk4_demod(sig, fs=48000.0, symrate=4800.0, init_spread=2.0, init_fine=0.0):
    d_symbol_time = symrate / fs
    d_symbol_clock = 0.0; d_symbol_spread = init_spread
    fine = init_fine; coarse = init_fine
    hist = [0.0] * NTAPS; last = 0; out = []; symbol_error = 0.0
    for x in sig:
        d_symbol_clock += d_symbol_time
        hist[last] = float(x); last = (last + 1) % NTAPS
        if d_symbol_clock > 1.0:
            d_symbol_clock -= 1.0
            imu = int(math.floor(0.5 + NSTEPS * (d_symbol_clock / d_symbol_time)))
            imu_p1 = imu + 1
            if imu >= NSTEPS: imu = NSTEPS - 1; imu_p1 = NSTEPS
            t_imu = TAPS[imu]; t_imu_p1 = TAPS[imu_p1]
            interp = 0.0; interp_p1 = 0.0; j = last
            for i in range(NTAPS):
                hj = hist[j]
                interp += t_imu[i] * hj
                interp_p1 += t_imu_p1[i] * hj
                j = (j + 1) % NTAPS
            interp -= fine; interp_p1 -= fine
            out.append(2.0 * interp / d_symbol_spread)
            if interp < -d_symbol_spread:
                symbol_error = interp + 1.5 * d_symbol_spread; d_symbol_spread -= symbol_error * 0.5 * K_SYMBOL_SPREAD
            elif interp < 0.0:
                symbol_error = interp + 0.5 * d_symbol_spread; d_symbol_spread -= symbol_error * K_SYMBOL_SPREAD
            elif interp < d_symbol_spread:
                symbol_error = interp - 0.5 * d_symbol_spread; d_symbol_spread += symbol_error * K_SYMBOL_SPREAD
            else:
                symbol_error = interp - 1.5 * d_symbol_spread; d_symbol_spread += symbol_error * 0.5 * K_SYMBOL_SPREAD
            if interp_p1 < interp: d_symbol_clock += symbol_error * K_SYMBOL_TIMING
            else:                  d_symbol_clock -= symbol_error * K_SYMBOL_TIMING
            if d_symbol_spread > SPREAD_MAX: d_symbol_spread = SPREAD_MAX
            elif d_symbol_spread < SPREAD_MIN: d_symbol_spread = SPREAD_MIN
            coarse += (fine - coarse) * K_COARSE_FREQUENCY
            fine += symbol_error * K_FINE_FREQUENCY
    return out
