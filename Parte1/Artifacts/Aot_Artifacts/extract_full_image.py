#!/usr/bin/env python3
"""
extract_full_image.py - rebuild the hidden file using the values that
derive_parameters.py worked out (params.json). No coordinates or orders
are hardcoded here.

For every frame from start_frame on, read the least significant bit at each
(y, x, channel) in bit_sequence_yxc, in that order, and append the bits to
one long stream. Pack the bits into bytes, skip prefix_bytes, and cut the
result to the file size given by the file's own header.

Usage:
    python3 derive_parameters.py "video.mkv"      # writes params.json
    python3 extract_full_image.py "video.mkv"     # writes hidden.* files
"""
import json
import struct
import argparse
import numpy as np


def iter_video_frames(path):
    import av
    container = av.open(path)
    stream = container.streams.video[0]
    for i, frame in enumerate(container.decode(stream)):
        yield i, frame.to_ndarray(format='rgb24')


def extract(frames, params):
    seq = np.array(params["bit_sequence_yxc"])
    Y, X, C = seq[:, 0], seq[:, 1], seq[:, 2]
    start = params["start_frame"]
    need = params.get("frames_needed")
    chunks = []
    for i, arr in frames:
        if i < start:
            continue
        chunks.append((arr[Y, X, C] & 1).astype(np.uint8))
        n = len(chunks)
        if n % 2000 == 0:
            print(f"    ...{n} frames read", flush=True)
        if need is not None and n >= need:
            break
    print(f"Read {len(chunks)} frames")
    bits = np.concatenate(chunks)
    return np.packbits(bits, bitorder=params["bitorder"]).tobytes()


def chunk_walk(data):
    print("\n--- chunk walk ---")
    pos = 12
    while pos + 8 <= len(data):
        fourcc = data[pos:pos + 4]
        size = struct.unpack('<I', data[pos + 4:pos + 8])[0]
        print(f"  {fourcc!r} size={size} @{pos}")
        if not all(32 <= b < 127 for b in fourcc):
            print("   (not a valid chunk name - stopping)")
            break
        pos += 8 + size + (size & 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--params", default="params.json")
    a = ap.parse_args()

    with open(a.params) as f:
        params = json.load(f)
    print(f"Using {a.params}:")
    print(f"  grid X {params['grid_x']}")
    print(f"  grid Y {params['grid_y']}")
    print(f"  read order: {params['read_order']}")
    print(f"  prefix {params['prefix_bytes']} bytes, format {params['format']}, "
          f"frames needed {params['frames_needed']}")

    stream = extract(iter_video_frames(a.video), params)
    with open("payload_stream_full.bin", "wb") as f:
        f.write(stream)
    print(f"Wrote payload_stream_full.bin ({len(stream)} bytes, prefix included)")

    data = stream[params["prefix_bytes"]:]
    if params.get("file_size"):
        data = data[:params["file_size"]]

    ext = {"RIFF": ".webp" if b'WEBP' in data[8:12] else ".riff",
           "PNG": ".png", "GIF": ".gif", "ZIP": ".zip", "PDF": ".pdf",
           "7z": ".7z", "JPEG": ".jpg", "GZIP": ".gz"}.get(params["format"], ".bin")
    out = "hidden" + ext
    with open(out, "wb") as f:
        f.write(data)
    print(f"Wrote {out} ({len(data)} bytes)")

    if params["format"] == "RIFF":
        chunk_walk(data)

    try:
        from PIL import Image
        img = Image.open(out)
        img.load()
        print(f"\nDecoded OK: {img.size} {img.mode}")
        img.save("hidden_view.png")
        print("Saved hidden_view.png")
    except Exception as e:
        print(f"\nCould not open as an image: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
