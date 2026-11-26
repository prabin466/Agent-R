from datetime import datetime


def when(dates):
    parse = lambda p: datetime.max if p == "Present" else datetime.strptime(p.removeprefix("Expected "), "%B %Y")
    parts = dates.split(" - ")
    return parse(parts[-1]), parse(parts[0])

def latest(items):
    return sorted(items, key=lambda e: when(e["dates"]), reverse=True)

def entry(item, final, *head):
    lines = [" | ".join(h for h in head if h)]
    return "\n".join(lines + [f"- {final[b['id']]}" for b in item["bullets"] if b["id"] in final])

ORDER = {
    "non-tech": ["WORK EXPERIENCE", "LICENCES & CLEARANCES", "EDUCATION", "SKILLS", "LANGUAGES"],
    "tech": ["SKILLS", "EDUCATION", "PROJECTS", "WORK EXPERIENCE", "LICENCES & CLEARANCES", "LANGUAGES"],
}
ORDER["adjacent"] = ORDER["tech"]

def render(master, final, skills, summaries, kind):
    final = final | {summaries[e["id"]]: master.bullets[summaries[e["id"]]] for e in master.data["experience"] if e["bullets"] and not any(b["id"] in final for b in e["bullets"])}
    d, c = master.data, master.data["contact"]
    sections = {
        "WORK EXPERIENCE": [entry(e, final, e["title"], e["org"], e["dates"]) for e in latest(d["experience"])],
        "LICENCES & CLEARANCES": [" · ".join(d["licences_clearances"])],
        "EDUCATION": [entry(e, final, e["degree"], e["org"], e["dates"]) for e in latest(d["education"])],
        "SKILLS": [" · ".join(skills)],
        "LANGUAGES": [" · ".join(d["languages"])],
        "PROJECTS": [entry(p, final, p["name"], p["context"]) for p in d["projects"] if any(b["id"] in final for b in p["bullets"])],
    }
    head = [c["name"], " · ".join([c["location"], c["phone"], c["email"], c["linkedin"]])]
    return "\n".join(head + [f"\n{t}\n" + "\n".join(sections[t]) for t in ORDER[kind] if sections[t]])
