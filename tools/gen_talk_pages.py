#!/usr/bin/env python3
"""gen_talk_pages — raw 동영상(연설)을 위키 소스 페이지로 일괄 지식화한다.

각 raw 동영상에 대해:
  - 제목에서 연사/주제를 분리
  - 전사본에서 성구 인용을 추출(한국어 정경으로 정규화)
  - wiki/sources/<slug>.md 소스 페이지 생성
집계 결과로:
  - wiki/entities/<연사>.md  (연사별 연설 목록)
  - wiki/scriptures/<책>.md   (성경 책별 인용 구절 → 인용한 연설)
  - index.md 전체 재생성 (wiki/ 디렉터리를 스캔)

요약(한 줄)은 제목의 '주제'를 사용한다(추출형). 개별 연설의 심층 요약은
필요할 때 해당 전사본을 읽어 따로 작성한다.

사용법:
    python tools/gen_talk_pages.py            # 전체 생성
    python tools/gen_talk_pages.py --dry-run  # 생성하지 않고 통계만
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import jwlib  # noqa: E402
import jwscripture as js  # noqa: E402

RAW_VID = ROOT / "raw" / "videos"
WIKI = ROOT / "wiki"

# 생성기가 건드리지 않는, 손으로 큐레이션한 페이지 (clobber 방지)
SKIP_RAW = {"StudioMonthlyPrograms"}     # 졸업식 영상 등은 별도 큐레이션


def parse_frontmatter(text: str):
    """간단한 frontmatter 파서. (dict, body) 반환. title 내부 따옴표는 그대로 둠."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    fm_block = text[3:end].strip("\n")
    body = text[end + 4:].lstrip("\n")
    fm = {}
    for line in fm_block.splitlines():
        m = re.match(r"^([a-zA-Z_]+):\s?(.*)$", line)
        if m:
            k, v = m.group(1), m.group(2).strip()
            if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
                v = v[1:-1]
            fm[k] = v
    return fm, body


# 연사명 표기 정규화 — raw 제목의 표기 변형을 정본으로 통일한다.
# (raw 원본은 불변이므로, 성구 정규화와 마찬가지로 생성 단계에서 흡수한다.)
SPEAKER_ALIASES = {
    "마크 누메어": "마크 누매어",
    "재프리 W. 잭슨": "제프리 W. 잭슨",
    "제프리 잭슨": "제프리 W. 잭슨",
}


def split_speaker(title: str):
    """'연사: 주제' → (연사, 주제). 연사가 없으면 (None, title)."""
    m = re.match(r"^([^:：]{2,22}):\s*(.+)$", title)
    if not m:
        return None, title
    left, right = m.group(1).strip(), m.group(2).strip()
    # 연사명 판별: 문장형(서술 어미)·따옴표 시작은 제외
    if left[0] in "\"'“‘《「『" or re.search(r"(다|요|오|시오|까|함)$", left):
        return None, title
    # "2026 기념식 아침 숭배—마크 샌더슨" 같은 접두 수식은 마지막 — 뒤를 연사로
    if "—" in left:
        left = left.split("—")[-1].strip()
    left = SPEAKER_ALIASES.get(left, left)
    return left, right


def transcript_body(body: str):
    """소스 raw 본문에서 전사본 텍스트만 추출. 없으면 ''."""
    m = re.search(r"^##[^\n]*transcript[^\n]*\)\s*$", body, re.M)
    if not m:
        # '## 자막 전사본' 형식 (괄호 표기가 달라도) 매칭
        m = re.search(r"^##[^\n]*전사본[^\n]*$", body, re.M)
    if not m:
        return ""
    rest = body[m.end():].strip()
    if "자막을 찾지 못했습니다" in rest:
        return ""
    return rest


def lead_excerpt(transcript: str, lang: str, n: int = 3):
    lines = [l.strip() for l in transcript.splitlines() if l.strip()]
    lines = lines[:n]
    return " ".join(lines)


def book_anchor(ref: str) -> str:
    book = js.book_of(ref)
    return f"[[scriptures/{book}|{ref}]]"


# --------------------------------------------------------------------------- #
def collect():
    talks = []
    for f in sorted(RAW_VID.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        if fm.get("category") in SKIP_RAW:
            continue
        title = fm.get("title", f.stem)
        speaker, theme = split_speaker(title)
        # 제목 괄호 안의 핵심 성구 추출 후, 표시용 주제에서는 그 괄호를 제거
        key_ref = js.parse_title_scripture(title)
        if key_ref:
            theme = re.sub(r"\s*\([^()]*\)\s*$", "", theme).strip()
        tlang = fm.get("transcript_lang", "") or "KO"
        tr = transcript_body(body)
        scriptures = js.extract(tr, tlang) if tr else []
        # 핵심 성구를 성구 목록 맨 앞에 (중복 제거)
        if key_ref and key_ref not in scriptures:
            scriptures = [key_ref] + scriptures
        talks.append({
            "slug": f.stem, "raw": f.name, "title": title,
            "speaker": speaker, "theme": theme, "key_ref": key_ref,
            "tlang": tlang if tr else "none",
            "transcript": tr, "scriptures": scriptures, "fm": fm,
        })
    return talks


def write_source_page(t):
    fm = t["fm"]
    tl_label = {"KO": "한국어 자막", "none": "전사본 없음(자막 미발행)"}.get(
        t["tlang"], f"{t['tlang']} 자막(한국어 미발행, 폴백)")
    lines = [
        "---", "type: source", "source_type: video",
        f'title: "{t["title"]}"',
    ]
    if t["speaker"]:
        lines.append(f'speaker: "{t["speaker"]}"')
    lines += [
        f'theme: "{t["theme"]}"',
        f"category: {fm.get('category', '')}",
        f"source_url: {fm.get('source_url', '')}",
        f"raw: ../../raw/videos/{t['raw']}",
        f"media_key: {fm.get('media_key', '')}",
        f"duration: {fm.get('duration', '')}",
        f"first_published: {fm.get('first_published', '')}",
        f"transcript_lang: {t['tlang']}",
        "date: 2026-06-06",
    ]
    if t.get("key_ref"):
        lines.append(f'key_scripture: "{t["key_ref"]}"')
    if t["scriptures"]:
        lines.append("scriptures: [" + ", ".join(f'"{s}"' for s in t["scriptures"]) + "]")
    tags = ["연설"]
    if t["speaker"]:
        tags.append(t["speaker"])
    lines.append(f"tags: [{', '.join(tags)}]")
    lines += ["---", "", f"# {t['title']}", ""]

    meta = []
    if t["speaker"]:
        meta.append(f"- **연사**: [[entities/{t['speaker']}]]")
    meta.append(f"- **주제**: {t['theme']}")
    if t.get("key_ref"):
        meta.append(f"- **핵심 성구**: {book_anchor(t['key_ref'])}")
    meta.append(f"- **길이**: {fm.get('duration','?')} · 공개: {fm.get('first_published','')[:10]}")
    meta.append(f"- **전사본**: {tl_label}")
    lines += meta + [""]

    if t["transcript"]:
        lead = lead_excerpt(t["transcript"], t["tlang"])
        head = "## 도입부 (전사본 발췌)"
        if t["tlang"] not in ("KO", "none"):
            head += " — ⚠️ 영어 자막 기반"
        lines += [head, "", lead, ""]
    else:
        lines += ["## 전사본", "",
                  "_이 영상은 한국어·영어 자막이 모두 발행되지 않아 전사본이 없습니다. "
                  "메타데이터만 보유합니다._", ""]

    if t["scriptures"]:
        lines += ["## 인용 성구", ""]
        lines += [f"- {book_anchor(s)}" for s in t["scriptures"]]
        lines += [""]

    lines += ["## 관련 페이지", ""]
    rel = []
    if t["speaker"]:
        rel.append(f"[[entities/{t['speaker']}]]")
    rel.append("[[overview]]")
    lines.append(" · ".join(rel))
    lines += ["", "## 출처",
              f"- 동영상: <{fm.get('source_url','')}>",
              f"- 전사본 원본: [[raw/videos/{t['slug']}]]"]
    if t["tlang"] not in ("KO", "none"):
        lines.append("- ⚠️ 한국어 자막 미발행 → 영어 자막을 전사·요약 근거로 사용.")
    (WIKI / "sources" / f"{t['slug']}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_speaker_pages(talks):
    speakers = {}
    for t in talks:
        if t["speaker"]:
            speakers.setdefault(t["speaker"], []).append(t)
    for name, ts in speakers.items():
        lines = ["---", "type: entity", "entity_type: person",
                 f'title: "{name}"', "tags: [인물, 연사]", "---", "",
                 f"# {name}", "",
                 f"여호와의 증인 출판물의 연설자. 이 위키에 수집된 연설 **{len(ts)}편**.", "",
                 "## 연설 목록", ""]
        for t in sorted(ts, key=lambda x: x["fm"].get("first_published", ""), reverse=True):
            date = t["fm"].get("first_published", "")[:10]
            lines.append(f"- [[sources/{t['slug']}|{t['theme']}]]" +
                         (f" ({date})" if date else ""))
        lines += ["", "## 관련 페이지", "[[overview]]", ""]
        (WIKI / "entities" / f"{name}.md").write_text("\n".join(lines), encoding="utf-8")
    return speakers


def write_scripture_book_pages(talks):
    books = {}   # book -> {ref -> [talk]}
    for t in talks:
        for ref in t["scriptures"]:
            b = js.book_of(ref)
            books.setdefault(b, {}).setdefault(ref, []).append(t)
    for book, refs in books.items():
        total = sum(len(v) for v in refs.values())
        lines = ["---", "type: scripture", "scripture_type: book",
                 f'title: "{book}"', "tags: [성구, 성경책]", "---", "",
                 f"# {book}", "",
                 f"이 위키의 소스들이 「{book}」에서 인용한 구절 {len(refs)}곳 "
                 f"(총 {total}회 인용).", "",
                 "## 인용된 구절", ""]
        def vkey(r):
            m = re.search(r"(\d+)", r)
            return int(m.group(1)) if m else 0
        for ref in sorted(refs, key=vkey):
            talks_citing = refs[ref]
            links = ", ".join(f"[[sources/{t['slug']}|{(t['speaker'] or t['theme'])[:16]}]]"
                              for t in talks_citing)
            lines.append(f"- **{ref}** — {links}")
        lines += ["", "## 관련 페이지", "[[overview]]", ""]
        (WIKI / "scriptures" / f"{book}.md").write_text("\n".join(lines), encoding="utf-8")
    return books


def rebuild_index():
    """wiki/ 를 스캔해 index.md 를 재생성한다 (큐레이션 페이지 포함, 항상 정확)."""
    def page_title(f):
        txt = f.read_text(encoding="utf-8")
        fm, _ = parse_frontmatter(txt)
        return fm.get("title", f.stem)

    def one_line(f):
        fm, body = parse_frontmatter(f.read_text(encoding="utf-8"))
        if fm.get("theme"):
            return fm["theme"]
        for line in body.splitlines():
            s = line.strip()
            if s and not s.startswith("#") and not s.startswith("-") and not s.startswith(">"):
                return s[:80]
        return ""

    out = ["# Index — JW Wiki 카탈로그", "",
           "위키 전체 페이지 목록. 질의 시 이 파일을 먼저 읽고 관련 페이지로 드릴다운한다.",
           "`tools/gen_talk_pages.py` 가 자동 재생성한다. → [개요](wiki/overview.md)", ""]
    sections = [("소스 (sources)", "sources"), ("개념 (concepts)", "concepts"),
                ("인물·연사 (entities)", "entities"), ("성구 (scriptures)", "scriptures")]
    for label, sub in sections:
        d = WIKI / sub
        files = sorted(d.glob("*.md"))
        if not files:
            continue
        out.append(f"## {label}  ({len(files)})")
        for f in files:
            t = page_title(f)
            summ = one_line(f)
            rel = f.relative_to(ROOT)
            out.append(f"- [{t}]({rel})" + (f" — {summ}" if summ else ""))
        out.append("")
    (ROOT / "index.md").write_text("\n".join(out), encoding="utf-8")


def mark_ingested(talks):
    for t in talks:
        f = RAW_VID / t["raw"]
        txt = f.read_text(encoding="utf-8")
        txt = txt.replace("ingested: false", "ingested: true", 1)
        f.write_text(txt, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    talks = collect()
    with_tr = [t for t in talks if t["transcript"]]
    speakers = {t["speaker"] for t in talks if t["speaker"]}
    all_refs = {r for t in talks for r in t["scriptures"]}
    books = {js.book_of(r) for r in all_refs}
    print(f"연설 {len(talks)}편 · 전사본 {len(with_tr)} · 연사 {len(speakers)}명 · "
          f"성구 {len(all_refs)}곳 · 성경책 {len(books)}권")
    if args.dry_run:
        return

    for t in talks:
        write_source_page(t)
    sp = write_speaker_pages(talks)
    bk = write_scripture_book_pages(talks)
    rebuild_index()
    mark_ingested(talks)
    print(f"생성: 소스 {len(talks)} · 연사 {len(sp)} · 성경책 {len(bk)} · index.md 재생성 완료")


if __name__ == "__main__":
    main()
