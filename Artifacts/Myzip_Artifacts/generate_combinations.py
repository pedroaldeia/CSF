"""
generate_combinations.py — builds a custom wordlist out of combinations of
words from subtitles.srt, then cracks myzip.zip with John the Ripper,
following the exact workflow from CSF Tutorial 1 ("Cracking Passwords",
p.6-8): zip2john -> john --wordlist -> john --show.

The tutorial's own dictionary attack only tries the packaged RockYou
wordlist (one candidate per line, real-world leaked passwords). That's
the right first move, but it only tests single "real" passwords people
have actually used elsewhere — it will never contain a password that's a
whole sentence made up for this exercise, like
"Ishouldbebackinaboutaweekorso". So this script builds a second,
case-specific wordlist (as the tutorial itself suggests as a follow-up
when RockYou comes up empty: "a case-specific wordlist or appropriate
transformation rules may be attempted next") out of combinations of
words taken from subtitles.srt, and feeds THAT to John instead.

Usage:
    python3 generate_combinations.py

Requires: John the Ripper + its zip2john helper on PATH
    sudo apt install -y john wordlists
and, next to this script: myzip.zip and subtitles.srt (path set below).
"""
import subprocess, sys, re, shutil, itertools
from pathlib import Path

# ---------------------------------------------------------------------
# Config — adjust these if your file layout differs
# ---------------------------------------------------------------------
ZIP_PATH = Path('myzip.zip')
SRT_PATH = Path('subtitles.srt')
RESULTS_DIR = Path('results')
HASH_FILE = RESULTS_DIR / 'protected.hash'
WORDLIST_FILE = RESULTS_DIR / 'srt-combinations.txt'

# =======================================================================
# PART 1 — build candidates out of combinations of subtitles.srt words
# =======================================================================

# --- 1a. Parse the .srt into cleaned dialogue lines ---------------------
raw = SRT_PATH.read_text(encoding='utf-8')
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

print(f"[+] parsed {len(lines)} dialogue lines from {SRT_PATH}")


def tokenize(line):
    return re.findall(r"[A-Za-z']+", line)


# --- 1b. n-grams: consecutive words within the SAME line ---------------
bigrams, trigrams, fourgrams = set(), set(), set()
for line in lines:
    words = [w for w in tokenize(line) if len(w) >= 2]
    for i in range(len(words) - 1):
        bigrams.add((words[i], words[i + 1]))
    for i in range(len(words) - 2):
        trigrams.add((words[i], words[i + 1], words[i + 2]))
    for i in range(len(words) - 3):
        fourgrams.add((words[i], words[i + 1], words[i + 2], words[i + 3]))

print(f"[+] {len(bigrams)} bigrams, {len(trigrams)} trigrams, "
      f"{len(fourgrams)} fourgrams")

# --- 1c. distinctive keywords (names / proper nouns) for pairwise combos
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
print(f"[+] {len(keywords)} distinctive keywords")

# --- 1d. generate candidates --------------------------------------------
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
# removed/underscored/hyphenated (this is where "Ishouldbebackinabout-
# aweekorso" actually comes from: a full sentence with spaces stripped)
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

candidates.discard('')
print(f"[+] {len(candidates)} total candidates generated")

RESULTS_DIR.mkdir(exist_ok=True)
WORDLIST_FILE.write_text('\n'.join(sorted(candidates)) + '\n', encoding='utf-8')
print(f"[+] wordlist written to {WORDLIST_FILE}")

# =======================================================================
# PART 2 — hand the wordlist to John the Ripper (CSF Tutorial 1, p.6-8)
# =======================================================================
for tool in ('zip2john', 'john'):
    if shutil.which(tool) is None:
        sys.exit(f"[!] '{tool}' not found on PATH. Install with:\n"
                  f"    sudo apt install -y john wordlists")


def run(cmd):
    print(f"\n$ {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True)


# Step 1: convert the zip's encryption info into John's hash format
RESULTS_DIR.mkdir(exist_ok=True)
r = run(['zip2john', str(ZIP_PATH)])
HASH_FILE.write_text(r.stdout)
print(r.stderr.strip())
print(f"[+] hash written to {HASH_FILE}")

# Step 2: dictionary attack using the SRT-combination wordlist
r = run(['john', f'--wordlist={WORDLIST_FILE}', str(HASH_FILE)])
print(r.stdout)
print(r.stderr.strip())

# Step 3: show the recovered password (works even on a re-run, since John
# caches cracked hashes in ~/.john/john.pot)
r = run(['john', '--show', str(HASH_FILE)])
print(r.stdout)