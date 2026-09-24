#!/usr/bin/env python3
"""
Extracts a hidden message encoded in the frame durations of an
animated WebP.

Each frame's duration, minus the 50ms baseline, is added to a running
total (wrapping at 256) to produce one byte per frame. The resulting
byte stream is written out as ASCII.

Usage:
    python3 extract_secret.py polish_cow.webp
"""

import struct
import argparse


def iter_anmf_frames(data):
    offset = 12
    while offset + 8 <= len(data):
        fourcc = data[offset:offset + 4]
        (size,) = struct.unpack_from("<I", data, offset + 4)
        payload_start = offset + 8
        payload_end = payload_start + size
        if payload_end > len(data):
            break
        if fourcc == b"ANMF":
            yield data[payload_start:payload_start + 16]  # frame_params
        offset = payload_end + (size & 1)


def parse_duration(frame_params):
    return int.from_bytes(frame_params[12:15], "little")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file")
    ap.add_argument("-o", "--out", default="polish_cow_secret.txt")
    args = ap.parse_args()

    with open(args.file, "rb") as f:
        data = f.read()

    durations = [parse_duration(fp) for fp in iter_anmf_frames(data)]

    prev = 0
    message = []
    for d in durations:
        value = (d - 50 + prev) % 256
        char = chr(value) if 32 <= value < 127 else "."
        message.append(char)
        prev = value

    with open(args.out, "w") as f:
        f.write("".join(message))

    print(f"Secret written to {args.out}")


if __name__ == "__main__":
    main()