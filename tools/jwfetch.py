#!/usr/bin/env python3
"""jwfetch — JW 출판물 URL을 받아 위키에 넣을 깨끗한 원본(raw) 파일로 만든다.

사용법:
    python tools/jwfetch.py <URL> [<URL> ...]
    python tools/jwfetch.py --json <URL>      # 결과 메타데이터를 JSON으로 출력

동작:
  - 동영상 URL  → raw/videos/<slug>.md   (메타데이터 + 자막 전사본)
  - 기사   URL  → raw/articles/<slug>.md (메타데이터 + 본문 마크다운 + 성경 인용)

이 스크립트는 *원본 수집*까지만 담당한다. 수집된 raw 파일을 읽고
위키 페이지로 지식화하는 일은 CLAUDE.md의 "수집(Ingest) 워크플로"에 따라
LLM 에이전트가 수행한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import jwlib  # noqa: E402

RAW = ROOT / "raw"


def _fmt_duration(sec: float) -> str:
    sec = int(sec or 0)
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def write_video(v: "jwlib.VideoResult") -> Path:
    slug = jwlib.slugify(v.title)
    out = RAW / "videos" / f"{slug}.md"
    fm = [
        "---",
        "type: video",
        f"title: \"{v.title}\"",
        f"media_key: {v.media_key}",
        f"lang: {v.lang}",
        f"duration: {_fmt_duration(v.duration)}",
        f"category: {v.category}",
        f"first_published: {v.first_published}",
        f"source_url: {v.source_url}",
        f"video_url: {v.video_url}",
        f"subtitle_url: {v.subtitle_url}",
        f"transcript_lang: {v.transcript_lang}",
        f"fetched: {jwlib.now_iso()}",
        "ingested: false",
        "---",
        "",
        f"# {v.title}",
        "",
    ]
    if v.description:
        fm += ["## 설명", "", v.description, ""]
    label = "자막 전사본 (transcript)"
    if v.transcript_lang and v.transcript_lang != "KO":
        label += f" — ⚠️ {v.transcript_lang} 자막 (한국어 자막 미발행)"
    fm += [f"## {label}", ""]
    fm += [v.transcript if v.transcript else "_자막을 찾지 못했습니다._"]
    fm += [""]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(fm), encoding="utf-8")
    return out


def write_article(a: "jwlib.ArticleResult") -> Path:
    slug = jwlib.slugify(a.title)
    out = RAW / "articles" / f"{slug}.md"
    fm = [
        "---",
        "type: article",
        f"title: \"{a.title}\"",
        f"lang: {a.lang}",
        f"doc_id: {a.doc_id}",
        f"pub: {a.pub}",
        f"has_video: {str(a.has_video).lower()}",
        f"source_url: {a.source_url}",
        f"fetched: {jwlib.now_iso()}",
        "ingested: false",
    ]
    if a.scriptures:
        fm.append("scriptures:")
        fm += [f"  - \"{s}\"" for s in a.scriptures]
    fm += ["---", "", a.body_md, ""]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(fm), encoding="utf-8")
    return out


def _video_raw_path(media_key: str, title: str) -> Path:
    return RAW / "videos" / f"{jwlib.slugify(title)}.md"


def process_video(info: "jwlib.UrlInfo", sess) -> dict:
    v = jwlib.fetch_video(info, sess)
    path = write_video(v)
    return {
        "kind": "video", "title": v.title, "path": str(path.relative_to(ROOT)),
        "duration": _fmt_duration(v.duration), "category": v.category,
        "transcript_chars": len(v.transcript), "subtitle": bool(v.subtitle_url),
        "transcript_lang": v.transcript_lang,
    }


def process_article(info: "jwlib.UrlInfo", sess) -> dict:
    a = jwlib.fetch_article(info, sess)
    path = write_article(a)
    return {
        "kind": "article", "title": a.title, "path": str(path.relative_to(ROOT)),
        "doc_id": a.doc_id, "pub": a.pub, "scriptures": len(a.scriptures),
        "has_video": a.has_video, "body_chars": len(a.body_md),
    }


def _already_have(media_key: str) -> Path | None:
    """media_key로 이미 수집된 raw 동영상 파일이 있으면 그 경로를 반환."""
    for f in (RAW / "videos").glob("*.md"):
        head = f.read_text(encoding="utf-8")[:400]
        if f"media_key: {media_key}" in head:
            return f
    return None


def process_category(info: "jwlib.UrlInfo", sess, force: bool, limit: int | None,
                     quiet: bool) -> list:
    items = jwlib.fetch_category(info, sess)
    if limit:
        items = items[:limit]
    if not quiet:
        print(f"▶ 카테고리 '{info.category_key}' — 동영상 {len(items)}개 수집 시작")
    results = []
    for i, (title, key) in enumerate(items, 1):
        existing = None if force else _already_have(key)
        if existing:
            results.append({"kind": "video", "title": title, "skipped": True,
                            "path": str(existing.relative_to(ROOT))})
            if not quiet:
                print(f"  [{i}/{len(items)}] ⏭  이미 있음: {title}")
            continue
        try:
            # 카테고리 일괄 수집 시에도 각 동영상은 자기만의 mediaitems URL을 갖게 한다
            item_url = (f"https://www.jw.org/{info.lang}/라이브러리/동영상/"
                        f"#{info.lang}/mediaitems/{info.category_key}/{key}")
            vinfo = jwlib.UrlInfo(kind="video", url=item_url, lang=info.lang,
                                  media_key=key)
            res = process_video(vinfo, sess)
            results.append(res)
            if not quiet:
                print(f"  [{i}/{len(items)}] ✓ {res['title']}  "
                      f"({res['duration']}, 자막 {res['transcript_chars']}자)")
        except Exception as e:  # noqa: BLE001
            results.append({"kind": "video", "title": title, "media_key": key,
                            "error": str(e)})
            if not quiet:
                print(f"  [{i}/{len(items)}] ✗ {title}: {e}", file=sys.stderr)
    return results


def process(url: str, force: bool = False, limit: int | None = None,
            quiet: bool = False) -> list:
    info = jwlib.parse_url(url)
    sess = jwlib.http()
    if info.kind == "category":
        return process_category(info, sess, force, limit, quiet)
    if info.kind == "video":
        return [process_video(info, sess)]
    return [process_article(info, sess)]


def main(argv=None):
    ap = argparse.ArgumentParser(description="JW 출판물 URL을 raw 소스로 수집")
    ap.add_argument("urls", nargs="+",
                    help="jw.org / wol.jw.org 기사·동영상·카테고리 URL")
    ap.add_argument("--json", action="store_true", help="결과를 JSON으로 출력")
    ap.add_argument("--force", action="store_true",
                    help="이미 수집한 동영상도 다시 받기")
    ap.add_argument("--limit", type=int, default=None,
                    help="카테고리 수집 시 최대 개수")
    args = ap.parse_args(argv)

    results = []
    for url in args.urls:
        try:
            results += process(url, force=args.force, limit=args.limit,
                               quiet=args.json)
        except Exception as e:  # noqa: BLE001
            results.append({"url": url, "error": str(e)})
            print(f"✗ 실패: {url}\n  {e}", file=sys.stderr)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        ok = sum(1 for r in results if "error" not in r and not r.get("skipped"))
        skip = sum(1 for r in results if r.get("skipped"))
        err = sum(1 for r in results if "error" in r)
        print(f"\n요약: 신규 {ok} · 건너뜀 {skip} · 실패 {err}")
    return 0 if all("error" not in r for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
