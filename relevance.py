import json,sys
from pathlib import Path
from openinference.instrumentation import suppress_tracing
from tailor import select, IDS
from contextlib import nullcontext

for case in json.load(open("relevance_set.json")):
    must, never = set(case["must"]), set(case["never"])
    assert must | never <= set(IDS) and not must & never,"bad labels"

    with (nullcontext() if "--trace" in sys.argv else suppress_tracing()):
        picked  = {p.source_id for p in select(Path(case["jd"]).read_text())}

    print(case["jd"], f"must-recall={len(picked & must)}/{len(must)}", f"never-picks={len(picked & never)}",
          f"picked={len(picked)}", "| missed:", sorted(must - picked), "| wrong:", sorted(picked & never),
          "| other:", sorted(picked - must - never))