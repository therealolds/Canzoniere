#!/usr/bin/env python3
"""Fetch an accordiespartiti.it song page and extract its <pre> chords-above-
lyrics block into a plain monospace text file (for merge_pdf.py --web).

  py scripts/fetch_aes.py <url> <out.txt>

Requires the HTML already downloaded to aes_raw.html, OR fetches via urllib.
"""
import html
import re
import sys
import urllib.request

url, out = sys.argv[1], sys.argv[2]
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
m = re.search(r"<pre[^>]*>(.*?)</pre>", raw, re.S)
if not m:
    sys.exit("no <pre> block found")
pre = m.group(1)
pre = re.sub(r'<span class="titolo">(.*?)</span>', r"\1", pre, flags=re.S)
pre = re.sub(r"<[^>]+>", "", pre)
pre = html.unescape(pre)
open(out, "w", encoding="utf-8").write(pre)
print(f"wrote {out} ({len(pre)} chars)")
