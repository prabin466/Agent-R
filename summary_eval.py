import sys
from contextlib import nullcontext

from openinference.instrumentation import suppress_tracing

from tailor import Master, describe

m = Master(sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].endswith(".yaml") else "master_resume.yaml")
with (nullcontext() if "--trace" in sys.argv else suppress_tracing()):
    picks = describe([e for e in m.data["experience"] if e["bullets"]])
for k, i in picks.items():
    print(f"{k}: {m.bullets[i]}")
