#!/usr/bin/env python3
"""Extract a JSON payload hidden in JPEG quantized AC DCT coefficients."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import jpeglib


def zigzag_positions() -> list[tuple[int, int]]:
    positions = []
    for diagonal in range(15):
        values = []
        start = max(0, diagonal - 7)
        stop = min(7, diagonal) + 1
        for row in range(start, stop):
            column = diagonal - row
            values.append((row, column))
        positions.extend(reversed(values) if diagonal % 2 == 0 else values)
    return positions


def extract_bytes(image_path: Path) -> bytes:
    jpeg = jpeglib.read_dct(str(image_path))
    bits = []
    positions = zigzag_positions()

    # The payload is in luminance (Y), using AC coefficients only.
    for block in jpeg.Y.reshape(-1, 8, 8):
        for row, column in positions[1:]:
            coefficient = int(block[row, column])
            if abs(coefficient) > 1:
                bits.append(coefficient & 1)

    return bytes(
        sum(bits[index + offset] << (7 - offset) for offset in range(8))
        for index in range(0, len(bits) - 7, 8)
    )


def decode_json(data: bytes) -> dict:
    start = data.find(b"{")
    if start < 0:
        raise ValueError("No JSON object found in the extracted bit stream")

    text = data[start:].decode("ascii", errors="ignore")
    payload, _ = json.JSONDecoder().raw_decode(text)
    if not isinstance(payload, dict):
        raise ValueError("Extracted payload is not a JSON object")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument(
        "--dump",
        action="store_true",
        help="print the complete JSON, including any sensitive fields",
    )
    args = parser.parse_args()

    payload = decode_json(extract_bytes(args.image))
    if args.dump:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print("Valid JSON payload found")
    print("Keys:", ", ".join(payload))
    for key in ("type", "project_id", "client_email", "client_id"):
        if key in payload:
            print(f"{key}: {payload[key]}")
    print("private_key present:", "private_key" in payload)
    print("private_key_id present:", "private_key_id" in payload)


if __name__ == "__main__":
    main()