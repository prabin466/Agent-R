import json
import sys
from contextlib import nullcontext
from pathlib import Path

from openinference.instrumentation import suppress_tracing

from tailor import Master, select

master = Master("master_resume.yaml")
kinds = {c["jd"]: c["type"] for c in json.loads(Path("jd_types.json").read_text())}

for case in json.loads(Path("relevance_set.json").read_text()):
    must, never = set(case["must"]), set(case["never"])
    assert must | never <= set(master.bullets) and not must & never, "bad labels"

    with nullcontext() if "--trace" in sys.argv else suppress_tracing():
        picked = {
            p.source_id
            for p in select(master, Path(case["jd"]).read_text(), kinds[case["jd"]])
        }

    print(
        case["jd"],
        f"must-recall={len(picked & must)}/{len(must)}",
        f"never-picks={len(picked & never)}",
        f"picked={len(picked)}",
        "| missed:",
        sorted(must - picked),
        "| wrong:",
        sorted(picked & never),
        "| other:",
        sorted(picked - must - never),
    )
