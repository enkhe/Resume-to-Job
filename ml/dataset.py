"""Build a labeled training dataset for the job-role classifier.

Labels come *for free* from the harvest: every job in the JSearch raw cache was
returned by a specific role query, recorded in ``data/jsearch_raw/manifest.json``.
We map each fine-grained query role to a canonical job *category*, then assign each
unique job the category of the query (or majority of queries) that surfaced it.

This is the "owned dataset" for the MLOps model: it regenerates from the raw cache,
so every new harvest expands it and the model can be retrained (the model "updates").
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "jsearch_raw"
MANIFEST_PATH = RAW_DIR / "manifest.json"

# Map each harvest query role -> canonical category the classifier predicts.
ROLE_TO_CATEGORY: dict[str, str] = {
    "entry level software engineer": "Software Engineering",
    "junior software developer": "Software Engineering",
    "new grad software engineer": "Software Engineering",
    "full stack developer": "Full Stack",
    "front end developer": "Frontend",
    "back end developer": "Backend",
    "data analyst": "Data & Analytics",
    "business intelligence analyst": "Data & Analytics",
    "junior data scientist": "Data & Analytics",
    "data engineer": "Data & Analytics",
    "machine learning engineer": "Machine Learning / AI",
    "cloud engineer": "Cloud & DevOps",
    "devops engineer": "Cloud & DevOps",
    "cybersecurity analyst": "Cybersecurity",
    "information security analyst": "Cybersecurity",
    "IT support specialist": "IT Infrastructure & Support",
    "help desk technician": "IT Infrastructure & Support",
    "systems administrator": "IT Infrastructure & Support",
    "network engineer": "IT Infrastructure & Support",
    "database administrator": "IT Infrastructure & Support",
    "QA engineer": "QA & Testing",
    "mobile developer": "Mobile",
}

_MAX_DESC_CHARS = 2000


@dataclass(frozen=True, slots=True)
class LabeledDataset:
    ids: list[str]
    texts: list[str]
    labels: list[str]
    categories: list[str]          # sorted unique labels
    label_source: str
    data_fingerprint: str          # hash of (ids+labels), so retrains can detect data change

    def __len__(self) -> int:
        return len(self.ids)


def _job_text(rec: dict) -> str:
    title = (rec.get("job_title") or "").strip()
    desc = (rec.get("job_description") or "").strip()[:_MAX_DESC_CHARS]
    return f"{title}. {desc}".strip()


def build_dataset(raw_dir: Path = RAW_DIR) -> LabeledDataset:
    # Import here so this module is importable without the src package on older paths.
    import sys
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from src.adapters.inbound.api_provider.jsearch_job_parser import JSearchJobParser

    manifest = json.loads((raw_dir / "manifest.json").read_text())["calls"]
    file_role = {c["file"]: c["role"] for c in manifest.values()}
    parser = JSearchJobParser()

    # job_id -> {text, candidate categories from every query that returned it}
    job_text: dict[str, str] = {}
    job_cats: dict[str, list[str]] = {}
    for fname, role in file_role.items():
        category = ROLE_TO_CATEGORY.get(role)
        if category is None:
            continue
        fpath = raw_dir / fname
        if not fpath.exists():
            continue
        for rec in parser.extract_list(json.loads(fpath.read_text())):
            jid = rec.get("job_id")
            text = _job_text(rec)
            if not jid or not text.strip():
                continue
            job_text.setdefault(jid, text)
            job_cats.setdefault(jid, []).append(category)

    ids: list[str] = []
    texts: list[str] = []
    labels: list[str] = []
    for jid, cats in job_cats.items():
        # Majority category among the queries that surfaced this job (tie -> first seen).
        label = Counter(cats).most_common(1)[0][0]
        ids.append(jid)
        texts.append(job_text[jid])
        labels.append(label)

    categories = sorted(set(labels))
    fingerprint = hashlib.sha1(
        "".join(f"{i}:{l}" for i, l in sorted(zip(ids, labels))).encode("utf-8")
    ).hexdigest()[:16]

    return LabeledDataset(
        ids=ids,
        texts=texts,
        labels=labels,
        categories=categories,
        label_source="jsearch_harvest_manifest_role->category",
        data_fingerprint=fingerprint,
    )


if __name__ == "__main__":
    ds = build_dataset()
    from collections import Counter as _C
    print(f"Dataset: {len(ds)} labeled jobs across {len(ds.categories)} categories")
    print(f"Fingerprint: {ds.data_fingerprint}")
    for cat, n in _C(ds.labels).most_common():
        print(f"  {n:>4}  {cat}")
