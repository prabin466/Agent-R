import os, sys, yaml
from pathlib import Path
from typing import Literal
from openai import OpenAI
from pydantic import BaseModel
from tracing import tracer   # also loads .env

client = OpenAI()
raw = Path("master_resume.yaml").read_text()
m = yaml.safe_load(raw)
BULLETS = {b["id"]: b["text"] for s in ("experience", "projects", "education") for e in m[s] for b in e["bullets"]}
IDS = tuple(BULLETS)
SKILLS = tuple(s for v in m["skills"].values() for s in v)

class Bullet(BaseModel):
    source_id: Literal[IDS]
    text: str

class Resume(BaseModel):
    fit_score: int
    fit_reason: str
    bullets: list[Bullet]
    skills: list[Literal[SKILLS]]

class Verdict(BaseModel):
    source_id: Literal[IDS]
    ok: bool
    added: str          # the unsupported phrase; empty if ok

class Verdicts(BaseModel):
    items: list[Verdict]

GEN = """Pick the 6-10 bullets most relevant to the job and rewrite each in the job ad's terminology.
One bullet per source_id, no repeats. Keep every number and name.
Change words, not facts: no new duties, tools, numbers, outcomes, scope, or quality claims ("excellent", "efficiently").
Skills: the relevant ones. fit_score 1-10, honest."""

CHECK = """For each pair, ok=false if REWRITE states anything SOURCE does not: new duties, tools, numbers, outcomes, scope, or quality claims.
Same fact in different words is ok. Put the unsupported phrase in 'added'."""

def ask(rules, text, schema):
    return client.responses.parse(model=os.getenv("MODEL", "gpt-4o-mini"),
                                  instructions=rules, input=text, text_format=schema)

@tracer.chain()
def generate(jd: str) -> Resume:
    return ask(GEN, f"MASTER:\n{raw}\n\nJOB:\n{jd}", Resume).output_parsed

@tracer.chain()
def check(pairs: dict) -> list[Verdict]:
    text = "\n\n".join(f"{i}\nSOURCE: {p['source']}\nREWRITE: {p['rewrite']}" for i, p in pairs.items())
    return ask(CHECK, text, Verdicts).output_parsed.items

@tracer.agent()
def tailor(jd: str):
    res = generate(jd)
    bullets = {b.source_id: b.text for b in res.bullets}   # dict keyed by id = duplicates dropped
    checks = check({i: {"source": BULLETS[i], "rewrite": t} for i, t in bullets.items()})
    ok = {v.source_id for v in checks if v.ok}             # unchecked ids count as failed
    final = [t if i in ok else BULLETS[i] for i, t in bullets.items()]
    return res, checks, final

if __name__ == "__main__":
    res, checks, final = tailor(Path(sys.argv[1]).read_text())
    for v in checks:
        if not v.ok: print(f"REVERTED {v.source_id}: '{v.added}'")
    print(f"\nFit {res.fit_score}/10: {res.fit_reason}\n")
    for t in final: print("-", t)
    print("\nSkills:", ", ".join(res.skills))

