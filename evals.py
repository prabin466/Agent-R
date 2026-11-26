import json
import sys
from contextlib import nullcontext
from pathlib import Path

from openinference.instrumentation import suppress_tracing

from tailor import check

cases = json.loads(
    Path(
        next((a for a in sys.argv[1:] if a.endswith(".json")), "eval_set.json")
    ).read_text()
)

# what: build each judge input straight from the case; why: the eval no longer depends on any resume file
pairs = {
    f"c{i}": {"source": c["source"], "rewrite": c["rewrite"]}
    for i, c in enumerate(cases)
}


def run(batched):
    return check(pairs) if batched else {k: check({k: v})[k] for k, v in pairs.items()}


with nullcontext() if "--trace" in sys.argv else suppress_tracing():
    verdicts = run("--per-pair" not in sys.argv)

m = {"TP": 0, "FN": 0, "FP": 0, "TN": 0}
for k, c in zip(pairs, cases):
    v = verdicts[k]
    grounded = v.added.strip(' ."').lower() in c["rewrite"].lower()
    flagged = not v.ok and ("--guard" not in sys.argv or grounded)
    cell = (
        ("TP" if flagged else "FN")
        if c["label"] == "inflated"
        else ("FP" if flagged else "TN")
    )
    m[cell] += 1
    if cell in ("FN", "FP"):
        print(
            cell,
            c["source_id"],
            "| added:",
            verdicts[k].added or "-",
            "|",
            c["rewrite"],
            "\n   reason:",
            verdicts[k].reason,
        )

print(
    m,
    f"recall={m['TP'] / (m['TP'] + m['FN']):.2f}",
    f"precision={m['TP'] / max(m['TP'] + m['FP'], 1):.2f}",
)
