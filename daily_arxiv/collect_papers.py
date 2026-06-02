#!/usr/bin/env python3
"""Collect papers from multiple metadata sources into the existing JSONL format."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote_plus

import arxiv
import requests
import yaml


@dataclass
class Paper:
    source: str
    source_id: str
    title: str
    authors: list[str] = field(default_factory=list)
    summary: str = ""
    categories: list[str] = field(default_factory=list)
    venue: str = ""
    date: str = ""
    doi: str = ""
    arxiv_id: str = ""
    abs_url: str = ""
    pdf_url: str = ""
    links: dict[str, str] = field(default_factory=dict)
    keywords_matched: list[str] = field(default_factory=list)
    research_direction: str = ""
    priority: str = "Low"

    def to_json(self) -> dict[str, Any]:
        primary_id = self.arxiv_id or self.doi or self.source_id
        primary_url = self.abs_url or self.links.get("primary", "")
        return {
            "id": primary_id,
            "source": self.source,
            "source_id": self.source_id,
            "title": self.title,
            "authors": self.authors,
            "summary": self.summary,
            "categories": self.categories or [self.source],
            "comment": self.venue,
            "abs": primary_url,
            "pdf": self.pdf_url,
            "venue": self.venue,
            "date": self.date,
            "doi": self.doi,
            "arxiv_id": self.arxiv_id,
            "links": self.links,
            "keywords_matched": self.keywords_matched,
            "research_direction": self.research_direction,
            "priority": self.priority,
        }


def load_config(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def keyword_list(config: dict[str, Any]) -> list[str]:
    keywords = config.get("keywords", {})
    merged = []
    for key in ("high_priority", "include"):
        merged.extend(keywords.get(key, []))
    if not merged:
        merged = ["robot", "robotic", "manipulation", "VLA", "EEG", "BCI"]
    return list(dict.fromkeys(merged))


def matched_keywords(text: str, keywords: list[str]) -> list[str]:
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


def classify_paper(text: str, matches: list[str]) -> tuple[str, str]:
    lower = text.lower()
    if any(k in lower for k in ["eeg", "bci", "brain-computer", "brain computer", "motor imagery", "ssvep", "p300", "prosthetic"]):
        direction = "BCI-Robotics" if any(k in lower for k in ["robot", "prosthetic", "exoskeleton", "grasp", "arm", "hand"]) else "EEG-BCI"
    elif any(k in lower for k in ["vision-language-action", "vla", "foundation model", "embodied"]):
        direction = "VLA"
    elif any(k in lower for k in ["survey", "review", "benchmark", "dataset"]):
        direction = "Survey"
    else:
        direction = "Robotics"

    high_terms = [
        "vision-language-action",
        "vla",
        "robot foundation model",
        "robotic manipulation",
        "dexterous",
        "grasp",
        "robotic arm",
        "robotic hand",
        "prosthetic hand",
        "shared control",
    ]
    priority = "High" if any(t in lower for t in high_terms) else ("Medium" if len(matches) >= 2 else "Low")
    return direction, priority


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def dedupe(papers: list[Paper]) -> list[Paper]:
    seen: set[str] = set()
    unique: list[Paper] = []
    for paper in papers:
        keys = [
            f"doi:{paper.doi.lower()}" if paper.doi else "",
            f"arxiv:{paper.arxiv_id.lower()}" if paper.arxiv_id else "",
            f"title:{normalize_title(paper.title)}" if paper.title else "",
        ]
        if any(key and key in seen for key in keys):
            continue
        for key in keys:
            if key:
                seen.add(key)
        unique.append(paper)
    return unique


def collect_arxiv(config: dict[str, Any], keywords: list[str]) -> list[Paper]:
    source_config = config.get("sources", {}).get("arxiv", {})
    if not source_config.get("enabled", False):
        return []

    env_categories = os.environ.get("CATEGORIES")
    categories = [cat.strip() for cat in env_categories.split(",") if cat.strip()] if env_categories else source_config.get("categories", ["cs.RO"])
    max_results = int(source_config.get("max_results_per_category", 80))
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(source_config.get("recent_days", 3)))
    client = arxiv.Client(page_size=max_results, delay_seconds=3)
    papers: list[Paper] = []

    for category in categories:
        search = arxiv.Search(query=f"cat:{category}", max_results=max_results, sort_by=arxiv.SortCriterion.SubmittedDate)
        for result in client.results(search):
            published = result.published.astimezone(timezone.utc)
            text = f"{result.title}\n{result.summary}\n{' '.join(result.categories)}"
            matches = matched_keywords(text, keywords)
            if published < cutoff:
                continue
            if not matches:
                continue
            direction, priority = classify_paper(text, matches)
            arxiv_id = result.entry_id.rsplit("/", 1)[-1]
            papers.append(
                Paper(
                    source="arxiv",
                    source_id=arxiv_id,
                    arxiv_id=arxiv_id,
                    title=result.title,
                    authors=[author.name for author in result.authors],
                    summary=result.summary,
                    categories=result.categories or [category],
                    venue=result.comment or "arXiv",
                    date=published.date().isoformat(),
                    abs_url=result.entry_id,
                    pdf_url=result.pdf_url or "",
                    links={"primary": result.entry_id, "pdf": result.pdf_url or ""},
                    keywords_matched=matches,
                    research_direction=direction,
                    priority=priority,
                )
            )
    return papers


def collect_semantic_scholar(config: dict[str, Any], keywords: list[str]) -> list[Paper]:
    source_config = config.get("sources", {}).get("semantic_scholar", {})
    if not source_config.get("enabled", False):
        return []

    papers: list[Paper] = []
    fields = "title,abstract,authors,venue,year,publicationDate,externalIds,url,openAccessPdf"
    years = set(map(str, source_config.get("recent_years", [])))
    for query in source_config.get("queries", []):
        params = {"query": query, "limit": int(source_config.get("max_results_per_query", 20)), "fields": fields}
        try:
            resp = requests.get("https://api.semanticscholar.org/graph/v1/paper/search", params=params, timeout=20)
            resp.raise_for_status()
        except Exception as exc:
            print(f"Semantic Scholar query failed for {query!r}: {exc}")
            continue

        for item in resp.json().get("data", []):
            year = str(item.get("year") or "")
            if years and year not in years:
                continue
            title = item.get("title") or ""
            abstract = item.get("abstract") or ""
            text = f"{title}\n{abstract}\n{item.get('venue') or ''}"
            matches = matched_keywords(text, keywords)
            if not matches:
                continue
            external = item.get("externalIds") or {}
            open_pdf = (item.get("openAccessPdf") or {}).get("url") or ""
            direction, priority = classify_paper(text, matches)
            papers.append(
                Paper(
                    source="semantic_scholar",
                    source_id=item.get("paperId") or title,
                    title=title,
                    authors=[author.get("name", "") for author in item.get("authors", []) if author.get("name")],
                    summary=abstract,
                    categories=["semantic_scholar"],
                    venue=item.get("venue") or "Semantic Scholar",
                    date=item.get("publicationDate") or year,
                    doi=external.get("DOI", ""),
                    arxiv_id=external.get("ArXiv", ""),
                    abs_url=item.get("url") or "",
                    pdf_url=open_pdf,
                    links={"primary": item.get("url") or "", "pdf": open_pdf},
                    keywords_matched=matches,
                    research_direction=direction,
                    priority=priority,
                )
            )
    return papers


def collect_crossref(config: dict[str, Any], keywords: list[str]) -> list[Paper]:
    source_config = config.get("sources", {}).get("crossref", {})
    if not source_config.get("enabled", False):
        return []

    papers: list[Paper] = []
    years = set(map(str, source_config.get("recent_years", [])))
    for query in source_config.get("queries", []):
        params = {"query.bibliographic": query, "rows": int(source_config.get("max_results_per_query", 10)), "sort": "published", "order": "desc"}
        try:
            resp = requests.get("https://api.crossref.org/works", params=params, timeout=20)
            resp.raise_for_status()
        except Exception as exc:
            print(f"Crossref query failed for {query!r}: {exc}")
            continue

        for item in resp.json().get("message", {}).get("items", []):
            title = " ".join(item.get("title") or [])
            abstract = re.sub("<[^>]+>", "", item.get("abstract") or "")
            published = item.get("published-print") or item.get("published-online") or {}
            date_parts = published.get("date-parts") or [[]]
            year = str(date_parts[0][0]) if date_parts and date_parts[0] else ""
            if years and year not in years:
                continue
            text = f"{title}\n{abstract}\n{' '.join(item.get('container-title') or [])}"
            matches = matched_keywords(text, keywords)
            if not matches:
                continue
            authors = []
            for author in item.get("author", []):
                name = " ".join(part for part in [author.get("given"), author.get("family")] if part)
                if name:
                    authors.append(name)
            direction, priority = classify_paper(text, matches)
            doi = item.get("DOI", "")
            url = item.get("URL", "")
            papers.append(
                Paper(
                    source="crossref",
                    source_id=doi or url or title,
                    title=title,
                    authors=authors,
                    summary=abstract,
                    categories=["crossref"],
                    venue="; ".join(item.get("container-title") or []) or "Crossref",
                    date=year,
                    doi=doi,
                    abs_url=url,
                    links={"primary": url, "doi": f"https://doi.org/{doi}" if doi else ""},
                    keywords_matched=matches,
                    research_direction=direction,
                    priority=priority,
                )
            )
    return papers


def write_scholar_fallback(config: dict[str, Any], output: str) -> None:
    source_config = config.get("sources", {}).get("google_scholar", {})
    if not source_config.get("enabled", False):
        return
    path = os.path.splitext(output)[0] + "_scholar_queries.txt"
    with open(path, "w", encoding="utf-8") as f:
        for query in source_config.get("queries", []):
            f.write(f"{query}\thttps://scholar.google.com/scholar?q={quote_plus(query)}\n")


def sort_date_value(date_text: str) -> int:
    if not date_text:
        return 0
    try:
        return int(datetime.fromisoformat(date_text).strftime("%Y%m%d"))
    except ValueError:
        return int(date_text[:4]) * 10000 if date_text[:4].isdigit() else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="daily_arxiv/config.yaml")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    config = load_config(args.config)
    keywords = keyword_list(config)
    papers: list[Paper] = []
    papers.extend(collect_arxiv(config, keywords))
    papers.extend(collect_semantic_scholar(config, keywords))
    papers.extend(collect_crossref(config, keywords))
    papers = dedupe(papers)
    priority_rank = {"High": 0, "Medium": 1, "Low": 2}
    papers.sort(key=lambda p: (priority_rank.get(p.priority, 9), -sort_date_value(p.date), normalize_title(p.title)))

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for paper in papers:
            f.write(json.dumps(paper.to_json(), ensure_ascii=False) + "\n")
    write_scholar_fallback(config, args.output)
    print(f"Wrote {len(papers)} papers to {args.output}")


if __name__ == "__main__":
    main()
