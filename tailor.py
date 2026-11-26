import json
import os
import sys
from pathlib import Path
from typing import Literal

import yaml
from openai import OpenAI
from pydantic import BaseModel, create_model

from render import render
from tracing import tracer  # also loads .env

client = OpenAI()
MODEL = os.getenv("MODEL", "gpt-4o-mini")
JUDGE = os.getenv("JUDGE_MODEL", "gpt-4o")
PICKER = os.getenv("PICKER_MODEL", "gpt-4o")


class Judgement(BaseModel):
    reason: str
    ok: bool
    added: str


class JobType(BaseModel):
    reason: str
    type: Literal["tech", "non-tech", "adjacent"]


class Master:
    def __init__(self, path: str):
        self.path = Path(path)
        self.data = yaml.safe_load(self.path.read_text())
        self.bullets = {
            b["id"]: b["text"]
            for s in ("experience", "projects", "education")
            for e in self.data[s]
            for b in e["bullets"]
        }
        self.section = {
            b["id"]: s
            for s in ("experience", "projects", "education")
            for e in self.data[s]
            for b in e["bullets"]
        }
        self.skills = tuple(s for v in self.data["skills"].values() for s in v)
        Id = Literal[tuple(self.bullets)]
        Bullet = create_model("Bullet", source_id=Id, text=str)
        self.Resume = create_model(
            "Resume",
            fit_score=int,
            fit_reason=str,
            bullets=list[Bullet],
            skills=list[Literal[self.skills]],
        )


GEN = """Rewrite each bullet under BULLETS in the job ad's terminology.
One bullet per source_id, no repeats. Keep every number and name.
Change words, not facts: no new duties, tools, numbers, outcomes, scope, or quality claims ("excellent", "efficiently").
Skills: the relevant ones. fit_score 1-10, honest."""

CHECK = """For each pair, ok=false if REWRITE states anything SOURCE does not: new duties, tools, numbers, outcomes, scope, or quality claims.
A quality claim is any word that praises the work or its result, even a single word: how well it was done (e.g. "efficiently", "excellent") or how complete or reliable the result is (e.g. "robust", "seamless").
Scope inflation is a stronger verb that claims more responsibility than SOURCE shows (e.g. "led" for "helped").
Same fact in different words is ok. Omitting SOURCE details is ok. 'added' must quote the unsupported phrase exactly as it appears in REWRITE."""

SELECT = """Pick the 8-10 bullets that best show the duties in the job ad.
For each pick, first quote the job-ad duty it shows, then give its id. One id per pick, no repeats.
Skip duties no bullet clearly shows; a duty may have several bullets."""

CLASSIFY = """Classify the job by the core of its duties, not by tools it mentions.
tech: the job builds or maintains code or data systems (software, pipelines, SQL, data cleaning).
adjacent: the job is domain expertise or analysis (finance, statistics, risk) where tech tools are only the means.
non-tech: hands-on, customer or physical work; computers are everyday tools (POS, email, basic Excel, admin).
First give a one-sentence reason naming the core duties, then the type."""

OVERVIEW = """For each job, pick the ONE bullet id that best explains what the job was overall: the role, the workplace and the main kind of work.
Pick only from that job's own bullets."""


def ask(rules, text, schema, model=MODEL, **kw):
    return client.responses.parse(
        model=model, instructions=rules, input=text, text_format=schema, **kw
    )


@tracer.chain()
def generate(master: Master, jd: str, ids: list[str]):
    text = "\n".join(f"{i}: {master.bullets[i]}" for i in ids)
    return ask(
        GEN,
        f"BULLETS:\n{text}\n\nSKILLS: {', '.join(master.skills)}\n\nJOB:\n{jd}",
        master.Resume,
    ).output_parsed


@tracer.chain()
def select(master: Master, jd: str, kind: str | None = None) -> list:
    # non-tech resumes have no Projects section, so project bullets are not offered (saves generate + judge calls)
    pool = {
        i: t
        for i, t in master.bullets.items()
        if not (kind == "non-tech" and master.section[i] == "projects")
    }
    Pick = create_model("Pick", duty=str, source_id=Literal[tuple(pool)])
    Selection = create_model("Selection", picks=list[Pick])
    text = "\n".join(f"{i}: {t}" for i, t in pool.items())
    return ask(
        SELECT, f"BULLETS:\n{text}\n\nJOB:\n{jd}", Selection, model=PICKER
    ).output_parsed.picks


@tracer.chain()
def classify(jd: str) -> JobType:
    return ask(CLASSIFY, f"JOB:\n{jd}", JobType, temperature=0).output_parsed


@tracer.chain()
def check(pairs: dict) -> dict[str, Judgement]:
    Vs = create_model("Verdicts", **{k: (Judgement, ...) for k in pairs})
    text = "\n\n".join(
        f"{i}\nSOURCE: {p['source']}\nREWRITE: {p['rewrite']}" for i, p in pairs.items()
    )
    return dict(ask(CHECK, text, Vs, model=JUDGE, temperature=0).output_parsed)


def sources(master: Master) -> dict[str, str]:
    def head(e):
        return (
            e["title"]
            + (f" at {e['org']}" if e.get("org") else "")
            + (" (current job)" if e["dates"].endswith("Present") else "")
            + ":"
        )

    return {
        e["id"]: " ".join([head(e)] + [b["text"] for b in e["bullets"]])
        for e in master.data["experience"]
        if e["bullets"]
    }


@tracer.chain()
def describe(jobs: list) -> dict[str, str]:
    Picks = create_model(
        "Overviews",
        **{e["id"]: (Literal[tuple(b["id"] for b in e["bullets"])], ...) for e in jobs},
    )
    text = "\n\n".join(
        f"{e['id']} ({e['title']}):\n"
        + "\n".join(f"{b['id']}: {b['text']}" for b in e["bullets"])
        for e in jobs
    )
    return ask(OVERVIEW, text, Picks, temperature=0).output_parsed.model_dump()


@tracer.chain()
def summarize(master: Master) -> dict[str, str]:
    cache = master.path.with_suffix(".summaries.json")
    old = json.loads(cache.read_text()) if cache.exists() else {}
    src = sources(master)
    # redo a job if its text changed OR its cached pick is no longer one of ITS bullets (renamed/moved id)
    fresh = lambda e: (
        old.get(e["id"], {}).get("source") == src[e["id"]]
        and old[e["id"]].get("id") in {b["id"] for b in e["bullets"]}
    )
    todo = [e for e in master.data["experience"] if e["id"] in src and not fresh(e)]
    new = (
        {k: {"source": src[k], "id": i} for k, i in describe(todo).items()}
        if todo
        else {}
    )
    keep = {k: old[k] for k in src if k in old} | new
    cache.write_text(json.dumps(keep, indent=1))
    return {k: v["id"] for k, v in keep.items()}


@tracer.agent()
def tailor(master: Master, jd: str):
    kind = classify(jd).type
    ids = list(dict.fromkeys(p.source_id for p in select(master, jd, kind)))
    res = generate(master, jd, ids)
    bullets = {b.source_id: b.text for b in res.bullets if b.source_id in ids}
    checks = {
        i: check({i: {"source": master.bullets[i], "rewrite": t}})[i]
        for i, t in bullets.items()
    }
    ok = {k for k, j in checks.items() if j.ok}
    final = {i: bullets[i] if i in ok else master.bullets[i] for i in ids}
    return res, checks, final, kind


if __name__ == "__main__":
    master = Master(sys.argv[1])
    jd = Path(sys.argv[2]).read_text()
    res, checks, final, kind = tailor(master, jd)
    for k, j in checks.items():
        if not j.ok:
            print(f"REVERTED {k}: added '{j.added}'")
    print(f"\nFit {res.fit_score}/10: {res.fit_reason}\n")
    print(render(master, final, res.skills, summarize(master), kind))
