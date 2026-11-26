import json
import sys
from collections import Counter
from contextlib import nullcontext
from pathlib import Path

from openinference.instrumentation import suppress_tracing

from tailor import classify

split = "test" if "--test" in sys.argv else "dev"
cases = [
    c for c in json.loads(Path("jd_types.json").read_text()) if c["split"] == split
]
confusion = Counter()

for c in cases:
    with nullcontext() if "--trace" in sys.argv else suppress_tracing():
        got = classify(Path(c["jd"]).read_text())
    confusion[(c["type"], got.type)] += 1
    if got.type != c["type"]:
        print(f"MISS {c['jd']}: want {c['type']}, got {got.type} | {got.reason}")

right = sum(n for (w, g), n in confusion.items() if w == g)
print(f"\n{split} accuracy: {right}/{len(cases)}")
for (w, g), n in sorted(confusion.items()):
    print(f"  {w:9} -> {g:9} {n}")
