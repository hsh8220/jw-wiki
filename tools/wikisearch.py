#!/usr/bin/env python3
"""wikisearch — 위키 마크다운 전문(全文) 검색 (의존성 없음).

index.md만으로 충분하지 않을 만큼 위키가 커졌을 때 쓴다.
제목/별칭 일치에 가중치를 주고, 본문 일치는 맥락 줄과 함께 보여 준다.

사용법:
    python tools/wikisearch.py "평화"
    python tools/wikisearch.py "요한복음 14:27" --raw   # raw/도 함께 검색
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def search(query: str, include_raw: bool):
    terms = [t for t in re.split(r"\s+", query.strip()) if t]
    roots = [ROOT / "wiki"]
    if include_raw:
        roots.append(ROOT / "raw")
    results = []
    for base in roots:
        for f in base.rglob("*.md"):
            text = f.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            title = next((l[1:].strip() for l in lines if l.startswith("# ")), f.stem)
            score, hits = 0, []
            low_title = title.lower()
            for t in terms:
                tl = t.lower()
                if tl in low_title:
                    score += 10
                for i, l in enumerate(lines):
                    if tl in l.lower():
                        score += 1
                        if len(hits) < 3 and l.strip() and not l.startswith("#"):
                            hits.append(f"    {i+1}: {l.strip()[:100]}")
            if score:
                results.append((score, f.relative_to(ROOT), title, hits))
    results.sort(key=lambda r: -r[0])
    return results


def main():
    ap = argparse.ArgumentParser(description="위키 전문 검색")
    ap.add_argument("query")
    ap.add_argument("--raw", action="store_true", help="raw/ 원본도 검색")
    ap.add_argument("-n", type=int, default=15, help="표시 개수")
    args = ap.parse_args()

    res = search(args.query, args.raw)
    if not res:
        print("결과 없음")
        return
    for score, path, title, hits in res[: args.n]:
        print(f"[{score:3d}] {title}  —  {path}")
        for h in hits:
            print(h)


if __name__ == "__main__":
    main()
