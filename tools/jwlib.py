"""jwlib — JW 온라인 출판물(jw.org / wol.jw.org) 수집을 위한 공용 라이브러리.

이 모듈은 두 가지 일을 한다:
  1) URL을 분석해 "동영상"인지 "기사"인지 판별한다.
  2) 각 유형에 맞는 깨끗한 원본(raw) 데이터를 추출한다.
     - 동영상: JW mediator API로 메타데이터를 받고 .vtt 자막을 읽기 쉬운 본문으로 변환.
     - 기사 : HTML의 <article> 본문을 마크다운으로 변환하고 성경 인용을 구조화.

이 모듈은 "지식화"를 하지 않는다. 그것은 LLM(에이전트)의 몫이다.
이 모듈의 책임은 LLM이 위키로 정리하기 좋은 *정확하고 깨끗한 원본*을 만드는 것까지다.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) jw-wiki/1.0"
MEDIATOR = "https://b.jw-cdn.org/apis/mediator/v1/media-items/{lang}/{key}"
PUBMEDIA = "https://b.jw-cdn.org/apis/pub-media/GETPUBMEDIALINKS"

# jw.org 페이지 URL의 로케일(ko, en …)을 mediator/pub-media가 쓰는 JW 언어 심볼로 매핑.
# 대부분은 로케일 대문자가 그대로 통하지만(KO), 영어/스페인어 등은 별도 심볼을 쓴다.
LOCALE_TO_SYMBOL = {
    "en": "E", "es": "S", "pt": "T", "fr": "F", "de": "X", "it": "I",
    "ja": "J", "ko": "KO", "zh": "CHS", "ru": "U", "ar": "A",
}


def http():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "ko,en;q=0.8"})
    return s


def slugify(text: str, maxlen: int = 70) -> str:
    """한글을 보존하면서 파일명으로 안전한 슬러그를 만든다."""
    text = unicodedata.normalize("NFC", text or "").strip()
    text = re.sub(r"[—–\-—–]+", "-", text)        # 각종 대시 → -
    text = re.sub(r"[^\w가-힣ㄱ-ㅎㅏ-ㅣ\s-]", "", text)      # 한글/영숫자/공백/하이픈만
    text = re.sub(r"\s+", "-", text).strip("-")
    return (text[:maxlen].rstrip("-") or "untitled")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


# --------------------------------------------------------------------------- #
# URL 분석
# --------------------------------------------------------------------------- #
@dataclass
class UrlInfo:
    kind: str                      # "video" | "article" | "category"
    url: str
    lang: str = "ko"               # 페이지 로케일 (소문자)
    media_key: Optional[str] = None  # 동영상: pub-...._VIDEO 형태의 lank
    category_key: Optional[str] = None  # 카테고리: 예) StudioTalks
    note: str = ""


def parse_url(url: str) -> UrlInfo:
    """URL을 보고 동영상/기사/카테고리 여부와 핵심 식별자를 뽑아낸다."""
    url = url.strip()
    p = urlparse(url)
    frag = unquote(p.fragment)        # 예: ko/mediaitems/StudioFeatured/pub-jwb-138_1_VIDEO
    path = unquote(p.path)

    def _frag_lang(default="ko"):
        if frag:
            first = frag.split("/", 1)[0]
            if re.fullmatch(r"[a-z]{2,3}(-[a-z]+)?", first):
                return first
        return default

    # 0) 카테고리: 프래그먼트의 /categories/<KEY> (개별 _VIDEO 키가 없을 때)
    cm = re.search(r"/categories/([^/?#]+)", "/" + frag)
    if cm and "_VIDEO" not in frag:
        return UrlInfo(kind="category", url=url, lang=_frag_lang(),
                       category_key=cm.group(1))

    # 1) 동영상: 프래그먼트의 mediaitems 경로 또는 _VIDEO 키
    m = re.search(r"/(pub-[^/?#]+_VIDEO|docid-[^/?#]+_VIDEO)", "/" + frag + "/" + path)
    if m or "/mediaitems/" in ("/" + frag):
        lang = "ko"
        if frag:
            first = frag.split("/", 1)[0]
            if re.fullmatch(r"[a-z]{2,3}(-[a-z]+)?", first):
                lang = first
        key = m.group(1) if m else None
        if not key:
            # 프래그먼트 끝에서 키 추출
            key = frag.rstrip("/").split("/")[-1]
        return UrlInfo(kind="video", url=url, lang=lang, media_key=key)

    # 2) 기사: wol.jw.org 문서 또는 jw.org 라이브러리 기사
    lang = "ko"
    seg = [s for s in path.split("/") if s]
    if seg and re.fullmatch(r"[a-z]{2,3}(-[a-z]+)?", seg[0]):
        lang = seg[0]
    return UrlInfo(kind="article", url=url, lang=lang)


CATEGORIES = "https://b.jw-cdn.org/apis/mediator/v1/categories/{lang}/{key}?detailed=1"


# --------------------------------------------------------------------------- #
# 카테고리
# --------------------------------------------------------------------------- #
def fetch_category(info: UrlInfo, sess: Optional[requests.Session] = None,
                   recurse: bool = True) -> list:
    """카테고리에 속한 동영상 목록을 [(title, media_key), ...] 로 반환한다.

    하위 카테고리가 있으면 recurse=True일 때 재귀적으로 펼친다.
    media_key는 언어 독립 키(pub-..._VIDEO)를 우선 사용한다.
    """
    sess = sess or http()
    items, seen = [], set()
    last_err = None
    for sym in _lang_symbols(info.lang):
        r = sess.get(CATEGORIES.format(lang=sym, key=info.category_key), timeout=30)
        if r.status_code != 200:
            last_err = f"HTTP {r.status_code}"
            continue
        cat = (r.json() or {}).get("category") or {}
        for m in cat.get("media", []) or []:
            key = m.get("languageAgnosticNaturalKey") or m.get("naturalKey") or m.get("key")
            if key and key not in seen:
                seen.add(key)
                items.append((m.get("title", key), key))
        if recurse:
            for sub in cat.get("subcategories", []) or []:
                subkey = sub.get("key")
                if subkey:
                    sub_info = UrlInfo(kind="category", url=info.url,
                                       lang=sym.lower(), category_key=subkey)
                    for t, k in fetch_category(sub_info, sess, recurse=True):
                        if k not in seen:
                            seen.add(k)
                            items.append((t, k))
        if items:
            return items
    if last_err:
        raise RuntimeError(f"카테고리 조회 실패 ({info.category_key}): {last_err}")
    return items


# --------------------------------------------------------------------------- #
# 동영상
# --------------------------------------------------------------------------- #
@dataclass
class VideoResult:
    title: str
    lang: str
    media_key: str
    duration: float = 0.0
    first_published: str = ""
    category: str = ""
    description: str = ""
    video_url: str = ""
    subtitle_url: str = ""
    transcript: str = ""
    transcript_lang: str = ""      # 전사본이 실제로 어느 언어 자막에서 나왔는지 (KO, E …)
    source_url: str = ""


def _lang_symbols(locale: str):
    """시도할 JW 언어 심볼 후보 목록 (정확도 순)."""
    locale = locale.lower()
    cands = []
    if locale in LOCALE_TO_SYMBOL:
        cands.append(LOCALE_TO_SYMBOL[locale])
    cands.append(locale.upper())
    seen, out = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _subtitle_url(files: list) -> str:
    for f in files or []:
        su = (f.get("subtitles") or {}).get("url")
        if su:
            return su
    return ""


def _read_subtitle(sess, url: str) -> str:
    sr = sess.get(url, timeout=30)
    if not sr.ok:
        return ""
    # .vtt는 charset 헤더가 없어 requests가 latin-1로 오인한다 → UTF-8 강제
    return vtt_to_text(sr.content.decode("utf-8", "replace"))


def fetch_video(info: UrlInfo, sess: Optional[requests.Session] = None,
                subtitle_fallback=("E",)) -> VideoResult:
    """동영상 메타데이터 + 자막 전사본을 가져온다.

    메타데이터·제목은 요청 언어(예: 한국어)를 따른다.
    해당 언어에 자막(.vtt)이 없으면 subtitle_fallback 언어(기본: 영어 E)로 자막만 대체한다.
    """
    sess = sess or http()
    key = info.media_key
    last_err = None
    for sym in _lang_symbols(info.lang):
        r = sess.get(MEDIATOR.format(lang=sym, key=key), timeout=30)
        if r.status_code != 200:
            last_err = f"HTTP {r.status_code}"
            continue
        data = r.json()
        media = data.get("media") or []
        if not media:
            last_err = "mediator: media 비어있음"
            continue
        m = media[0]
        files = m.get("files") or []
        best = max(files, key=lambda f: f.get("bitRate", 0)) if files else {}

        sub_url = _subtitle_url(files)
        sub_lang = sym if sub_url else ""
        # 자막이 없으면 폴백 언어로 자막만 가져온다 (메타데이터는 그대로 유지)
        if not sub_url:
            for fb in subtitle_fallback:
                if fb == sym:
                    continue
                fr = sess.get(MEDIATOR.format(lang=fb, key=key), timeout=30)
                if not fr.ok:
                    continue
                fmedia = (fr.json() or {}).get("media") or []
                if not fmedia:
                    continue
                fb_url = _subtitle_url(fmedia[0].get("files") or [])
                if fb_url:
                    sub_url, sub_lang = fb_url, fb
                    break

        transcript = _read_subtitle(sess, sub_url) if sub_url else ""
        vurl = ""
        if isinstance(best.get("file"), dict):
            vurl = best["file"].get("url", "")
        vurl = best.get("progressiveDownloadURL") or vurl
        return VideoResult(
            title=m.get("title", key),
            lang=sym,
            media_key=key,
            duration=m.get("duration", 0.0),
            first_published=m.get("firstPublished", ""),
            category=m.get("primaryCategory", ""),
            description=m.get("description", "") or "",
            video_url=vurl,
            subtitle_url=sub_url,
            transcript=transcript,
            transcript_lang=sub_lang,
            source_url=info.url,
        )
    raise RuntimeError(f"동영상 메타데이터를 가져오지 못함 ({key}): {last_err}")


def vtt_to_text(vtt: str) -> str:
    """WebVTT 자막을 읽기 쉬운 본문으로 변환한다.

    타임스탬프/큐설정/번호를 제거하고, 줄을 이어 자연스러운 문단으로 만든다.
    연속 중복 줄(자막이 겹쳐 반복되는 경우)은 제거한다.
    """
    lines = []
    for raw in vtt.splitlines():
        s = raw.strip()
        if not s or s == "WEBVTT" or s.startswith(("NOTE", "STYLE", "Kind:", "Language:")):
            continue
        if "-->" in s:                       # 타임스탬프 줄
            continue
        if re.fullmatch(r"\d+", s):          # 큐 번호
            continue
        s = re.sub(r"<[^>]+>", "", s)        # 인라인 태그 제거
        s = re.sub(r"\s+", " ", s).strip()
        if s:
            lines.append(s)
    # 연속 중복 제거
    dedup = []
    for s in lines:
        if not dedup or dedup[-1] != s:
            dedup.append(s)
    text = " ".join(dedup)
    # 문장 끝(. ! ? 。 …)마다 줄바꿈을 넣어 가독성 확보
    text = re.sub(r"([.!?。…])\s+", r"\1\n", text)
    return text.strip()


# --------------------------------------------------------------------------- #
# 기사
# --------------------------------------------------------------------------- #
@dataclass
class ArticleResult:
    title: str
    lang: str
    doc_id: str = ""
    pub: str = ""
    scriptures: list = field(default_factory=list)
    body_md: str = ""
    has_video: bool = False
    source_url: str = ""


def fetch_article(info: UrlInfo, sess: Optional[requests.Session] = None) -> ArticleResult:
    sess = sess or http()
    r = sess.get(info.url, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    soup = BeautifulSoup(r.text, "lxml")

    art = soup.find(id="article") or soup.find("article") or soup.find(id="content") or soup.find("main")
    if art is None:
        raise RuntimeError("기사 본문(<article>)을 찾지 못함")

    # 메타데이터
    title = ""
    h1 = art.find("h1")
    if h1:
        title = h1.get_text(" ", strip=True)
    if not title:
        og = soup.find("meta", property="og:title")
        title = (og.get("content") if og else "") or (soup.title.string if soup.title else "untitled")
    title = re.sub(r"\s*[—\-]\s*워치타워 온라인 라이브러리.*$", "", title).strip()

    classes = " ".join(art.get("class", []))
    m_doc = re.search(r"docId-(\d+)", classes)
    doc_id = m_doc.group(1) if m_doc else ""
    m_pub = re.search(r"\bpub-([a-zA-Z0-9]+)\b", classes)
    pub = m_pub.group(1) if m_pub else ""

    has_video = bool(art.find("video"))

    # 성경 인용 (a.b 링크) — 중복 제거하며 순서 보존
    scriptures, seen = [], set()
    for a in art.select("a.b"):
        t = a.get_text(" ", strip=True).rstrip(",;").strip()
        if t and t not in seen:
            seen.add(t)
            scriptures.append(t)

    # 본문 정리: 불필요 요소 제거 후 마크다운 변환
    junk = ["script", "style", "nav", "noscript", ".docNav", ".secondaryNav",
            ".groupTOC", ".articleNavMobile", ".pubInfo", "#footer", ".pageNum",
            ".articleFootnotes ~ nav", ".tabContent .hide"]
    for sel in junk:
        for tag in art.select(sel):
            tag.decompose()

    body_html = str(art)
    body_md = md(body_html, heading_style="ATX", bullets="-")
    # 마크다운 후처리: 과도한 빈 줄/공백 정리
    body_md = re.sub(r"[ \t]+\n", "\n", body_md)
    body_md = re.sub(r"\n{3,}", "\n\n", body_md).strip()

    return ArticleResult(
        title=title, lang=info.lang, doc_id=doc_id, pub=pub,
        scriptures=scriptures, body_md=body_md, has_video=has_video,
        source_url=info.url,
    )
