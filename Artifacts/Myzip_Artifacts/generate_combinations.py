"""
generate_combinations.py — single, self-contained script.

Builds zip-password *candidates* out of combinations of words from
subtitles.srt (not just single words) and tests each one against
myzip.zip. No other files needed.

Usage:
    python3 generate_combinations.py

Requires just the standard library, and two files sitting next to this
script: myzip.zip, and subtitles.srt at the path set by SRT_PATH below.
"""
import sys, re, time, itertools, zipfile, struct, zlib

# ---------------------------------------------------------------------
# Config — adjust these if your file layout differs
# ---------------------------------------------------------------------
ZIP_PATH = 'myzip.zip'
ENTRY_NAME = 'amelia.pdf'
EXPECTED_MAGIC = b'%PDF'
SRT_PATH = 'subtitles.srt'

# =======================================================================
# PART 1 — the oracle: given a password guess, is it correct?
# =======================================================================
# Classic ZipCrypto encryption prepends a 12-byte encryption header to
# each entry. Decrypting that header with a candidate password should
# end in a "check byte" derived from the entry's own CRC32/mod-time
# (cheap first filter). If that passes, decrypting further and
# zlib-inflating the result should start with the target file's real
# magic bytes (tier2 — the actual proof, negligible false-positive rate).

_zf = zipfile.ZipFile(ZIP_PATH)
_info = _zf.getinfo(ENTRY_NAME)
with open(ZIP_PATH, 'rb') as _fh:
    _lho = _info.header_offset
    _fh.seek(_lho)
    _lh = _fh.read(30)
    _n_len, _e_len = struct.unpack('<HH', _lh[26:30])
    _fh.seek(_lho + 30 + _n_len + _e_len)
    _enc_header = _fh.read(12)
    _fh.seek(_lho + 30 + _n_len + _e_len + 12)
    _comp_prefix = _fh.read(4096)

_flag = _info.flag_bits
_yr, _mo, _dy, _hh, _mm, _ss = _info.date_time
_dostime = ((_hh & 0x1F) << 11) | ((_mm & 0x3F) << 5) | ((_ss // 2) & 0x1F)
# bit 3 set -> streamed entry (data descriptor used) -> check byte comes
# from the high byte of the DOS mod-time instead of the CRC32
_check_byte = (_dostime >> 8) & 0xFF if _flag & 0x8 else (_info.CRC >> 24) & 0xFF

_ZipDecrypter = zipfile._ZipDecrypter


def try_pw(pw):
    pb = pw.encode('latin-1', 'ignore') if isinstance(pw, str) else pw
    if not pb:
        return False

    # tier 1: 12-byte header check byte (fast, ~1/256 false-positive rate)
    dec = _ZipDecrypter(pb)
    h = dec(_enc_header)
    if h[11] != _check_byte:
        return False

    # tier 2: decrypt + inflate + check real file magic bytes
    dec = _ZipDecrypter(pb)
    dec(_enc_header)
    plain = dec(_comp_prefix)
    d = zlib.decompressobj(-15)  # raw deflate, no zlib/gzip header
    try:
        out = d.decompress(plain, len(EXPECTED_MAGIC))
        return out.startswith(EXPECTED_MAGIC)
    except Exception:
        return False


# =======================================================================
# PART 2 — build candidates out of combinations of subtitles.srt words
# =======================================================================

# --- 2a. Parse the .srt into cleaned dialogue lines ---------------------
raw = open(SRT_PATH, encoding='utf-8').read()
blocks = raw.strip().split('\n\n')

lines = []        # cleaned text: brackets/notes stripped, punctuation kept
raw_lines = []     # original text including brackets/punctuation
speakers = set()   # e.g. {'EREN', 'MIKASA', 'NARRATOR', ...}

for b in blocks:
    parts = b.split('\n')
    if len(parts) < 3:
        continue  # not a real subtitle block (index + timestamp + text)
    text = ' '.join(parts[2:])  # everything after the timestamp line
    raw_lines.append(text.strip())

    for m in re.finditer(r'\[([A-Z\' ]+)\]', text):
        speakers.add(m.group(1).strip())

    clean = re.sub(r'\[[^\]]*\]', ' ', text)   # drop [SPEAKER] tags
    clean = clean.replace('♪', ' ')        # drop music-note glyphs
    clean = re.sub(r'\s+', ' ', clean).strip()
    if clean:
        lines.append(clean)

print(f"parsed {len(lines)} dialogue lines", file=sys.stderr)


def tokenize(line):
    return re.findall(r"[A-Za-z']+", line)


# --- 2b. n-grams: consecutive words within the SAME line ---------------
bigrams, trigrams, fourgrams = set(), set(), set()
for line in lines:
    words = [w for w in tokenize(line) if len(w) >= 2]
    for i in range(len(words) - 1):
        bigrams.add((words[i], words[i + 1]))
    for i in range(len(words) - 2):
        trigrams.add((words[i], words[i + 1], words[i + 2]))
    for i in range(len(words) - 3):
        fourgrams.add((words[i], words[i + 1], words[i + 2], words[i + 3]))

print(f"{len(bigrams)} bigrams, {len(trigrams)} trigrams, "
      f"{len(fourgrams)} fourgrams", file=sys.stderr)

# --- 2c. distinctive keywords (names / proper nouns) for pairwise combos
keywords = set(speakers)
keywords.update([
    'Eren', 'Mikasa', 'Armin', 'Hannes', 'Carla', 'Keith', 'Hugo', 'Jaeger',
    'Shiganshina', 'Titan', 'Titans', 'Scout', 'Scouts', 'Regiment',
    'Garrison', 'Wall', 'Walls', 'Mankind', 'Humanity', 'Cattle', 'Pen',
    'Wardens', 'amelia', 'Amelia',
])
for line in lines:
    for w in tokenize(line):
        if w[:1].isupper() and len(w) >= 3:
            keywords.add(w)
keywords = sorted(k for k in keywords if k.isalpha())
print(f"{len(keywords)} distinctive keywords", file=sys.stderr)

# --- 2d. generate candidates --------------------------------------------
JOINERS = ['', ' ', '_', '-']
SUFFIXES = ['', '1', '12', '123', '!', '2026', '26', '01',
            '_2026', '2025', '2027']


def case_variants(s):
    return {s, s.lower(), s.upper(), (s[:1].upper() + s[1:].lower()) if s else s}


candidates = set()

# n-grams from actual dialogue, joined + cased + a few suffixes
for gram in list(bigrams) + list(trigrams) + list(fourgrams):
    for j in JOINERS:
        base = j.join(gram)
        for cv in case_variants(base):
            candidates.add(cv)
            for suf in SUFFIXES:
                if suf:
                    candidates.add(cv + suf)

# pairwise cross-combinations of distinctive keywords (both orders)
for a, b in itertools.permutations(keywords, 2):
    for j in ['', '_', '-']:
        base = a + j + b
        candidates.update({base, base.lower(), base.upper()})

# whole dialogue lines — verbatim, punctuation-stripped, and with spaces
# removed/underscored/hyphenated (THIS is where the real password came
# from: a full sentence with spaces stripped out)
for rl, cl in zip(raw_lines, lines):
    for s in (rl, cl):
        s = s.strip()
        if not s:
            continue
        candidates.add(s)
        stripped = re.sub(r"[^\w\s']", '', s).strip()
        if stripped:
            candidates.add(stripped)
            candidates.add(stripped.replace(' ', ''))
            candidates.add(stripped.replace(' ', '_'))
            candidates.add(stripped.replace(' ', '-'))

print(f"total candidates to test: {len(candidates)}", file=sys.stderr)

# =======================================================================
# PART 3 — test every candidate against the zip
# =======================================================================
start = time.time()
found = None
count = 0
for c in candidates:
    if not c:
        continue
    count += 1
    if try_pw(c):
        found = c
        break
    if count % 300000 == 0:
        print(count, round(time.time() - start, 1), 's', file=sys.stderr)

print("tested", count, "in", round(time.time() - start, 1), "s")
print("FOUND:", repr(found))
