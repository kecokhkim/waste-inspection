"""국가법령정보 OPEN API로 폐기물처리시설 검사 관련 법령 DB(data/laws.json)를 만든다.

사용법:  python tools/build_law_db.py
  - 저장소 최상위의 .env 에서 LAW_OC 를 읽는다.
  - 이 PC의 공인 IP가 open.law.go.kr 마이페이지에 등록되어 있어야 한다.
표준 라이브러리만 사용한다.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "laws.json")
API = "https://www.law.go.kr/DRF/"

# 수록 대상. 법령은 법령ID(개정돼도 바뀌지 않음), 행정규칙은 이름으로 찾는다.
LAWS = [
    {"id": "001771", "short": "법"},
    {"id": "005353", "short": "영"},
    {"id": "008567", "short": "규칙"},
]
ADMRULS = ["폐기물처리시설의 검사방법에 관한 규정"]

CHUNK = 1800  # 별표는 길어서 이 글자 수 단위로 나눈다


def load_env():
    env = {}
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    env.update({k: v for k, v in os.environ.items() if k in ("LAW_OC",)})
    return env


def get(svc, oc, **params):
    q = urllib.parse.urlencode(dict(OC=oc, type="JSON", **params))
    req = urllib.request.Request(API + svc + "?" + q, headers={"User-Agent": "waste-inspection-db/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
            break
        except Exception as e:  # 일시 오류는 재시도
            if attempt == 2:
                raise
            print(f"  재시도 ({e})")
            time.sleep(2 * (attempt + 1))
    if isinstance(data, dict) and data.get("result") and data.get("msg"):
        raise SystemExit(f"API 오류: {data['result']} {data['msg']}")
    if isinstance(data, dict) and isinstance(data.get("Law"), str):
        raise SystemExit(f"API 오류: {data['Law']}")
    time.sleep(0.4)  # 과도한 호출 방지
    return data


def arr(v):
    return [] if v is None else (v if isinstance(v, list) else [v])


def flat(v):
    """문자열 또는 중첩 리스트를 줄 단위 문자열로."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "\n".join(x for x in (flat(i) for i in v) if x)
    return str(v)


def ymd(s):
    s = str(s or "")
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else s


def chunks(lines, size):
    buf, n = [], 0
    for ln in lines:
        if buf and n + len(ln) > size:
            yield "\n".join(buf)
            buf, n = [], 0
        buf.append(ln)
        n += len(ln) + 1
    if buf:
        yield "\n".join(buf)


def article_text(u):
    out = []
    hangs = arr(u.get("항"))
    if not hangs:
        out.append(flat(u.get("조문내용")))
    else:
        out.append(flat(u.get("조문내용")))
        for h in hangs:
            if h.get("항내용"):
                out.append(flat(h["항내용"]))
            for ho in arr(h.get("호")):
                out.append("  " + flat(ho.get("호내용")))
                for mok in arr(ho.get("목")):
                    out.append("    " + flat(mok.get("목내용")))
    return "\n".join(x for x in out if x and x.strip()).strip()


def build_law(oc, spec, docs, sources):
    j = get("lawService.do", oc, target="law", ID=spec["id"])
    law = j.get("법령") or {}
    info = law.get("기본정보") or {}
    name = info.get("법령명_한글", "")
    ef = ymd(info.get("시행일자"))
    sources.append({"kind": "법령", "name": name, "id": spec["id"], "ef": ef,
                    "prom": ymd(info.get("공포일자")), "type": flat((info.get("법종구분") or {}).get("content"))})
    n_art = n_tab = 0
    for u in arr((law.get("조문") or {}).get("조문단위")):
        if u.get("조문여부") != "조문":
            continue
        no = int(u.get("조문번호") or 0)
        gaji = int(u.get("조문가지번호") or 0)
        label = f"제{no}조" + (f"의{gaji}" if gaji else "")
        text = article_text(u)
        if not text or re.search(r"^\s*제\d+조(의\d+)?\s*삭제", text):
            continue
        docs.append({"t": "law", "law": name, "lid": spec["id"], "kind": "조문", "jo": no, "gaji": gaji,
                     "cite": f"{name} {label}", "title": flat(u.get("조문제목")),
                     "ef": ymd(u.get("조문시행일자")) or ef, "text": text})
        n_art += 1
    for b in arr((law.get("별표") or {}).get("별표단위")):
        bno = int(b.get("별표번호") or 0)
        bg = int(b.get("별표가지번호") or 0)
        kind = flat(b.get("별표구분")) or "별표"
        if kind != "별표":
            continue  # 서식은 제외
        label = f"[별표 {bno}" + (f"의{bg}" if bg else "") + "]"
        lines = [ln.rstrip() for ln in flat(b.get("별표내용")).split("\n") if ln.strip()]
        parts = list(chunks(lines, CHUNK))
        for i, part in enumerate(parts, 1):
            docs.append({"t": "law-byul", "law": name, "lid": spec["id"], "kind": "별표", "byul": bno,
                         "cite": f"{name} {label}" + (f" ({i}/{len(parts)})" if len(parts) > 1 else ""),
                         "title": flat(b.get("별표제목")), "ef": ef, "text": part})
            n_tab += 1
    print(f"  {name}: 조문 {n_art}개, 별표 조각 {n_tab}개 (시행 {ef})")


def build_admrul(oc, name, docs, sources):
    s = get("lawSearch.do", oc, target="admrul", query=name, display=20)
    hit = next((x for x in arr((s.get("AdmRulSearch") or {}).get("admrul")) if x.get("행정규칙명") == name), None)
    if not hit:
        raise SystemExit(f"행정규칙을 찾지 못했습니다: {name}")
    j = get("lawService.do", oc, target="admrul", ID=hit["행정규칙일련번호"])
    r = j.get("AdmRulService") or {}
    info = r.get("행정규칙기본정보") or {}
    ef = ymd(info.get("시행일자"))
    sources.append({"kind": "행정규칙", "name": name, "id": info.get("행정규칙ID"), "ef": ef,
                    "prom": ymd(info.get("발령일자")), "type": info.get("행정규칙종류", "")})
    n_art = n_tab = 0
    for t in arr(r.get("조문내용")):
        t = flat(t).strip()
        m = re.match(r"^제(\d+)조(?:의(\d+))?\(([^)]*)\)", t)
        if not m:
            continue  # 장·절 제목
        no, gaji, title = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        label = f"제{no}조" + (f"의{gaji}" if gaji else "")
        text = re.sub(r"([^\s\d])(\d{1,2}\. )", r"\1\n\2", t)
        docs.append({"t": "admrul", "law": name, "kind": "조문", "jo": no, "gaji": gaji,
                     "cite": f"{name} {label}", "title": title, "ef": ef, "text": text})
        n_art += 1
    for b in arr((r.get("별표") or {}).get("별표단위")):
        bno = int(b.get("별표번호") or 0)
        lines = [ln.rstrip() for ln in flat(b.get("별표내용")).split("\n") if ln.strip()]
        parts = list(chunks(lines, CHUNK))
        for i, part in enumerate(parts, 1):
            docs.append({"t": "admrul-byul", "law": name, "kind": "별표", "byul": bno,
                         "cite": f"{name} [별표 {bno}]" + (f" ({i}/{len(parts)})" if len(parts) > 1 else ""),
                         "title": flat(b.get("별표제목")), "ef": ef, "text": part})
            n_tab += 1
    print(f"  {name}: 조문 {n_art}개, 별표 조각 {n_tab}개 (시행 {ef})")


def main():
    oc = load_env().get("LAW_OC")
    if not oc:
        raise SystemExit(".env 에 LAW_OC 가 없습니다.")
    docs, sources = [], []
    print("법령 DB 구축 시작")
    for spec in LAWS:
        build_law(oc, spec, docs, sources)
    for name in ADMRULS:
        build_admrul(oc, name, docs, sources)
    for i, d in enumerate(docs):
        d["i"] = i
    kst = timezone(timedelta(hours=9))
    out = {"built": datetime.now(kst).strftime("%Y-%m-%d %H:%M"), "sources": sources, "docs": docs}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"완료: {len(docs)}건 → {os.path.relpath(OUT, ROOT)} ({os.path.getsize(OUT)//1024} KB)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
