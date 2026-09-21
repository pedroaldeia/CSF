#!/usr/bin/env python3
"""
derive_parameters.py - work out, from the video alone, every value that
extract_full_image.py needs. Nothing is hardcoded except the list of
well-known file signatures used to recognise a correct decode.

Steps:
  1. Decode frames in order and find "black carrier" frames: every pixel
     value is 0 or 1, and at least one pixel is 1. In such a frame the only
     thing that differs from pure black is the least significant bit.
  2. Collect every (x, y) position that is 1 in any of those frames.
     The distinct X values and distinct Y values give the grid.
  3. Read the grid from frames 0, 1, 2, ... in every possible order
     (channel order, row order, column order, grouping, bit packing) and
     look for a known file signature. The order that produces a valid,
     structurally consistent header is the real one; the byte offset where
     the header starts is the prefix.
  4. If the file is RIFF, read its size field to find out how many frames
     the whole file needs.
  5. Write everything to params.json for extract_full_image.py.

Usage:
    python3 derive_parameters.py "video.mkv" [--out params.json]
"""
import sys
import json
import argparse
import itertools
import numpy as np


# ---------------------------------------------------------------- frames

def iter_video_frames(path):
    import av
    container = av.open(path)
    stream = container.streams.video[0]
    for i, frame in enumerate(container.decode(stream)):
        yield i, frame.to_ndarray(format='rgb24')


def is_black_carrier(arr):
    return arr.max() <= 1 and arr.any()


# ---------------------------------------------------------------- step 1+2

def find_grid(frames, keep_first=16, min_black=10, max_frames=5000):
    """Return (first frames, lit positions, black frame indices, frames scanned)."""
    head = []
    lit = set()
    black_idx = []
    scanned = 0
    for i, arr in frames:
        scanned = i + 1
        if i < keep_first:
            head.append(arr)
        if is_black_carrier(arr):
            ys, xs = np.nonzero((arr & 1).any(axis=2))
            lit |= set(zip(xs.tolist(), ys.tolist()))
            black_idx.append(i)
            nx = len({p[0] for p in lit})
            ny = len({p[1] for p in lit})
            complete = len(lit) == nx * ny
            if len(head) >= keep_first and len(black_idx) >= min_black and complete:
                break
        if scanned >= max_frames:
            break
    return head, lit, black_idx, scanned


# ---------------------------------------------------------------- step 3

def v_riff(d, i):
    """A RIFF header only counts if its sizes are consistent: the declared
    file size must be big enough, and each chunk must have a readable name
    and end inside the file. Score = 3 + number of chunks that check out."""
    form = d[i + 8:i + 12]
    if form not in (b'WEBP', b'WAVE', b'AVI '):
        return 0, "RIFF without a known form type"
    total = int.from_bytes(d[i + 4:i + 8], 'little') + 8
    if total < 20:
        return 0, f"RIFF size {total} is too small to be real"
    pos, good, names = i + 12, 0, []
    while pos + 8 <= len(d):
        name = d[pos:pos + 4]
        size = int.from_bytes(d[pos + 4:pos + 8], 'little')
        end = pos + 8 + size + (size & 1)
        if not all(32 <= b < 127 for b in name) or end - i > total:
            break
        good += 1
        names.append(f"{name.decode()}({size})")
        pos = end
    if good == 0:
        return 0, "RIFF whose first chunk does not fit"
    return 3 + good, (f"RIFF/{form.decode().strip()} file size={total}, "
                      f"chunks that check out: {' '.join(names)}")

def v_png(d, i):
    return (4, "PNG with IHDR") if d[i + 12:i + 16] == b'IHDR' else (2, "PNG signature")

SIGNATURES = [
    ("RIFF", b'RIFF', v_riff),
    ("PNG",  b'\x89PNG\r\n\x1a\n', v_png),
    ("GIF",  b'GIF8', lambda d, i: (3, "GIF") if d[i+4:i+6] in (b'7a', b'9a') else (0, "")),
    ("ZIP",  b'PK\x03\x04', lambda d, i: (2, "ZIP local header")),
    ("PDF",  b'%PDF-', lambda d, i: (2, "PDF")),
    ("7z",   b'7z\xbc\xaf\x27\x1c', lambda d, i: (3, "7z")),
    ("JPEG", b'\xff\xd8\xff', lambda d, i: (1, "JPEG SOI")),
    ("GZIP", b'\x1f\x8b\x08', lambda d, i: (1, "gzip")),
]


def all_orderings(xs, ys):
    for perm in itertools.permutations(range(3)):
        pname = ''.join('RGB'[c] for c in perm)
        for yrev in (False, True):
            for xrev in (False, True):
                Y = ys[::-1] if yrev else ys
                X = xs[::-1] if xrev else xs
                modes = {
                    "per channel, row by row":    [(y, x, c) for c in perm for y in Y for x in X],
                    "per channel, column by column": [(y, x, c) for c in perm for x in X for y in Y],
                    "per row, channel by channel": [(y, x, c) for y in Y for c in perm for x in X],
                    "per dot, all channels":       [(y, x, c) for y in Y for x in X for c in perm],
                }
                for mode, seq in modes.items():
                    for bitorder in ('big', 'little'):
                        yield {
                            "channel_order": pname,
                            "rows": "bottom to top" if yrev else "top to bottom",
                            "columns": "right to left" if xrev else "left to right",
                            "grouping": mode,
                            "bitorder": bitorder,
                            "seq": seq,
                        }


def stream_from(frames, seq, bitorder):
    Y = np.array([s[0] for s in seq]); X = np.array([s[1] for s in seq]); C = np.array([s[2] for s in seq])
    bits = np.concatenate([arr[Y, X, C] & 1 for arr in frames]).astype(np.uint8)
    return np.packbits(bits, bitorder=bitorder).tobytes()


def search_orderings(head, xs, ys):
    results = []
    seen_streams = {}
    for o in all_orderings(xs, ys):
        data = stream_from(head, o["seq"], o["bitorder"])
        key = data[:64]
        if key in seen_streams:
            seen_streams[key].append(o)
            continue
        seen_streams[key] = [o]
        for name, magic, validate in SIGNATURES:
            start = 0
            while True:
                i = data.find(magic, start)
                if i == -1:
                    break
                score, detail = validate(data, i)
                if score > 0:
                    results.append((score, i, name, detail, o, data))
                start = i + 1
    results.sort(key=lambda r: (-r[0], r[1]))
    return results, seen_streams


def describe(o):
    return (f"channels {o['channel_order']}, {o['grouping']}, rows {o['rows']}, "
            f"columns {o['columns']}, bit packing {o['bitorder']}-endian")


# ---------------------------------------------------------------- main

def derive(frames, out_path="params.json"):
    print("STEP 1-2: finding black carrier frames and the grid")
    head, lit, black_idx, scanned = find_grid(frames)
    if not lit:
        print("  no black carrier frames found - cannot derive the grid")
        return None
    xs = sorted({p[0] for p in lit})
    ys = sorted({p[1] for p in lit})
    print(f"  scanned {scanned} frames, {len(black_idx)} black carriers "
          f"(first few: {black_idx[:12]})")
    print(f"  {len(lit)} distinct lit positions")
    print(f"  distinct X: {xs}  gaps {[b - a for a, b in zip(xs, xs[1:])]}")
    print(f"  distinct Y: {ys}  gaps {[b - a for a, b in zip(ys, ys[1:])]}")
    print(f"  grid = {len(xs)} x {len(ys)} = {len(xs) * len(ys)} positions, "
          f"{len(lit)} of them seen lit")
    if len(xs) * len(ys) > 4 * len(lit):
        print("  WARNING: lit positions do not look like a grid")
    bits_per_frame = len(xs) * len(ys) * 3
    print(f"  => {bits_per_frame} bits = {bits_per_frame / 8:g} bytes per frame")

    print(f"\nSTEP 3: trying every read order on frames 0-{len(head) - 1}")
    results, groups = search_orderings(head, xs, ys)
    print(f"  {len(groups)} distinct byte streams tried")
    if not results:
        print("  no known file signature found in any order")
        return None
    print("  best candidates:")
    for score, off, name, detail, o, _ in results[:5]:
        print(f"    score {score}  {name} at byte {off:<4} {detail}")
        print(f"         {describe(o)}")
    score, prefix, name, detail, best, data = results[0]
    same = groups[data[:64]]
    if len(same) > 1:
        print(f"  ({len(same)} orderings give this identical stream; using the first)")
    runner_up = [r for r in results[1:] if r[0] == score]
    if runner_up:
        print(f"  NOTE: {len(runner_up)} other stream(s) tie on score - check them")

    print("\nSTEP 4: file size and frames needed")
    params = {
        "grid_x": xs,
        "grid_y": ys,
        "bit_sequence_yxc": [list(map(int, s)) for s in best["seq"]],
        "bitorder": best["bitorder"],
        "read_order": describe(best),
        "start_frame": 0,
        "prefix_bytes": prefix,
        "format": name,
        "header_detail": detail,
        "bits_per_frame": bits_per_frame,
        "black_frames_used": black_idx,
    }
    print(f"  header starts at byte {prefix} "
          f"(frame {prefix * 8 // bits_per_frame}), prefix = {prefix} bytes")
    if name == "RIFF":
        total = int.from_bytes(data[prefix + 4:prefix + 8], 'little') + 8
        params["file_size"] = total
        stream_bits = (prefix + total) * 8
        frames_needed = -(-stream_bits // bits_per_frame)
        params["file_size"] = total
        params["frames_needed"] = frames_needed
        print(f"  RIFF size field says the file is {total} bytes")
        print(f"  => {frames_needed} frames needed "
              f"(the black carriers alone are {len(black_idx)}+ frames)")
    else:
        params["file_size"] = None
        params["frames_needed"] = None
        print("  not RIFF - size unknown, extractor will read every frame")

    with open(out_path, "w") as f:
        json.dump(params, f, indent=2)
    print(f"\nWrote {out_path}")
    print(f"  read order: {params['read_order']}")
    print(f"  prefix: {prefix} bytes, frames needed: {params['frames_needed']}")
    return params


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", default="params.json")
    a = ap.parse_args()
    derive(iter_video_frames(a.video), a.out)


if __name__ == "__main__":
    main()
