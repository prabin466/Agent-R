import os, sys, yaml
from pathlib import Path
from typing import Literal
from openai import OpenAI
from pydantic import BaseModel, create_model
from tracing import tracer   # also loads .env

client = OpenAI()
raw = Path("master_resume.yaml").read_text()
m = yaml.safe_load(raw)
BULLETS = {b["id"]: b["text"] for s in ("experience", "projects", "education") for e in m[s] for b in e["bullets"]}
IDS = tuple(BULLETS)
SKILLS = tuple(s for v in m["skills"].values() for s in v)
JUDGE = os.getenv("JUDGE_MODEL", "gpt-4o")

class Bullet(BaseModel):
    source_id: Literal[IDS]
    text: str

class Resume(BaseModel):
    fit_score: int
    fit_reason: str
    bullets: list[Bullet]
    skills: list[Literal[SKILLS]]


class Judgement (BaseModel):
    ok:bool
    added:str

class Pick(BaseModel):
    duty:str
    source_id:Literal[IDS]

class Selection(BaseModel):
    picks:list[Pick]
 
GEN = """Rewrite each bullet listed under REWRITE ONLY in the job ad's terminology.
One bullet per source_id, no repeats. Keep every number and name.
Change words, not facts: no new duties, tools, numbers, outcomes, scope, or quality claims ("excellent", "efficiently").
Skills: the relevant ones. fit_score 1-10, honest."""

CHECK = """For each pair, ok=false if REWRITE states anything SOURCE does not: new duties, tools, numbers, outcomes, scope, or quality claims.
A quality claim is any judgement of how well the work was done, even a single word (e.g. "efficiently", "excellent").
Scope inflation is a stronger verb that claims more responsibility than SOURCE shows (e.g. "led" for "helped").
Same fact in different words is ok. Omitting SOURCE details is ok. 'added' must quote the unsupported phrase exactly as it appears in REWRITE."""

SELECT = """Pick the 8-10 bullets that best show the duties in the job ad.
For each pick, first quote the job-ad duty it shows, then give its id. One id per pick, no repeats.
Skip duties no bullet clearly shows; a duty may have several bullets."""

def ask(rules, text, schema,model=os.getenv("MODEL", "gpt-4o-mini"),**kw):
    return client.responses.parse(model=model,
                                  instructions=rules, input=text, text_format=schema, **kw)

@tracer.chain()
def generate(jd: str, ids: list[str]) -> Resume:
    return ask(GEN, f"MASTER:\n{raw}\n\nREWRITE ONLY: {', '.join(ids)}\n\nJOB:\n{jd}", Resume).output_parsed



@tracer.chain()
def select(jd:str) -> list[Pick]:
    text = "\n".join(f"{i}: {t}" for i, t in BULLETS.items())
    return ask(SELECT, f"BULLETS:\n{text}\n\nJOB:\n{jd}", Selection).output_parsed.picks
    

@tracer.chain()
def check(pairs: dict) -> dict[str,Judgement]:
    Vs = create_model("Verdicts", **{k: (Judgement, ...) for k in pairs})
    text = "\n\n".join(f"{i}\nSOURCE: {p['source']}\nREWRITE: {p['rewrite']}" for i, p in pairs.items())
    return dict(ask(CHECK, text, Vs, model=JUDGE, temperature=0).output_parsed)

@tracer.agent()
def tailor(jd: str):
    ids = list(dict.fromkeys(p.source_id for p in select(jd)))
    res = generate(jd, ids)
    bullets = {b.source_id: b.text for b in res.bullets if b.source_id in ids}
    checks = {i: check({i: {"source": BULLETS[i], "rewrite": t}})[i] for i, t in bullets.items()}
    ok = {k for k, j in checks.items() if j.ok}
    final = [bullets[i] if i in ok else BULLETS[i] for i in ids]
    return res, checks, final

if __name__ == "__main__":
    res, checks, final = tailor(Path(sys.argv[1]).read_text())
    for k, j in checks.items():
        if not j.ok:
            print(f"REVERTED {k}: added '{j.added}'")
    print(f"\nFit {res.fit_score}/10: {res.fit_reason}\n")
    for t in final: print("-", t)
    print("\nSkills:", ", ".join(res.skills))

