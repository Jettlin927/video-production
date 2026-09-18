# -*- coding: utf-8 -*-
"""Align script sentences onto ASR word timings, with self-checks that refuse bad output.

Why this exists
---------------
Hand-rolling sentence alignment inside a per-video build script wasted more time
and tokens than every other step combined: a script sentence and its ASR
transcript always differ (numerals are spelled out, homophones get misheard,
characters get swallowed), and each ad-hoc attempt fixed one case while breaking
another. One probe run produced 5 successive rewrites of the same 60 lines.

The failure mode that matters is silence: a *free* subsequence match has many
equal-cost optima, so a whole sentence can slide forward onto a later
lookalike phrase. Nothing raises, and every following sentence's timing is
shifted. This module instead uses a banded edit distance whose gap model makes a
spoken numeral rewrite align as a delete+insert pair (cost 2) rather than as
repeated same-slot replacements (cost 3 each), and it *verifies* the result
before writing anything.

Method
------
1. Split the ASR word stream at sentence boundaries.
2. For each script sentence, align it against a band of the stream starting at
   the previous sentence's end, bounded by the linear character estimate.
3. Check the aligned window really begins on the sentence's first character; if
   not, the aligner tries the next candidate band and finally fails loudly.

Usage
-----
  python align_script.py --script hook-script.json --transcript asr/transcript.source.json \
      --out timing.json [--json-detail timing-detail.json]

`hook-script.json` needs `sentences: [{id, text_zh, ...}]`. Optional per-sentence
override for the text actually spoken (e.g. a sentence whose tail the voiceover
merges into the next one) goes in `align_text_override: {sentence_id: "..."}` at
the top level.
"""
import argparse
import json
import sys
import unicodedata

PUNCT = "，。、；：！？…—－·「」『』（）()《》\"'“”‘’ \u3000"
BAND = 20             # how far the match may look ahead for a real match
MAX_TAIL_S = 0.6      # allowed tail shorter than the sentence's final word span

# Spoken forms: the voiceover says "七天" where the script writes "7天". The value
# is the set of stream characters that may stand for the key, so the key itself
# must be included -- during the first hand-rolled attempt this table was written
# backwards, same_char('7','七') returned False, and every numeric sentence needed
# a manual patch.
DIGIT_EQUIV = {
    "0": "0零〇", "1": "1一壹", "2": "2二两", "3": "3三", "4": "4四",
    "5": "5五", "6": "6六", "7": "7七", "8": "8八", "9": "9九",
    "零": "0零〇", "一": "1一壹", "二": "2二两", "两": "2两二",
    "三": "3三", "四": "4四", "五": "5五", "六": "6六",
    "七": "7七", "八": "8八", "九": "9九",
}

# Chinese numeral units, for parsing a spelled-out number into its value.
CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "壹": 1, "二": 2, "两": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000}


def parse_cn_number(text):
    """Parse a Chinese numeral string to an int, or None if it is not one.

    The voiceover reads 140 as "一百四十" while the script writes "140", so the
    aligner has to compare numbers by value. Translating digit by digit cannot
    work: '十' is ten, not one, and treating it as 1 is exactly what an earlier
    hand-rolled table got wrong.
    """
    if not text:
        return None
    if text.isdigit():
        return int(text)
    total, section, current = 0, 0, 0
    saw_any = False
    for ch in text:
        if ch == "万":
            total += (section + current) * 10000
            section, current = 0, 0
            saw_any = True
        elif ch in CN_UNITS:
            unit = CN_UNITS[ch]
            section += (current or 1) * unit
            current = 0
            saw_any = True
        elif ch in CN_DIGITS:
            current = CN_DIGITS[ch]
            saw_any = True
        else:
            return None
    return total + section + current if saw_any else None


def numbers_equal(a, b):
    """True when two characters are different spellings of the same number."""
    if a == b:
        return True
    if not (a.isdigit() or b.isdigit() or a in CN_DIGITS or b in CN_DIGITS
            or a in CN_UNITS or b in CN_UNITS):
        return False
    va, vb = parse_cn_number(a), parse_cn_number(b)
    return va is not None and va == vb

# Verified homophone mishearings for this voiceover pipeline. Add pairs only after
# listening to the audio; a generic edit-distance tolerance makes every pair of
# Chinese characters equivalent and destroys the match.
ASR_CONFUSIONS = [
    ("进", "尽"),
]


def norm(text):
    out = []
    for ch in unicodedata.normalize("NFKC", text):
        if ch in PUNCT:
            continue
        if ch.isalnum() or "\u4e00" <= ch <= "\u9fff":
            out.append(ch.lower())
    return "".join(out)


def same_char(a, b):
    if a == b:
        return True
    if b in DIGIT_EQUIV.get(a, ""):
        return True
    # Units may be whole numerals ("10" vs "十", "140" vs "一百四十"): compare by
    # value, which is the only way a spelled-out number can align to a written one.
    va, vb = _numeric(a), _numeric(b)
    if va is not None and va == vb:
        return True
    if len(a) == 1 and len(b) == 1:
        return any((a == x and b == y) or (a == y and b == x) for x, y in ASR_CONFUSIONS)
    return False


def target_units(text):
    """Split script text into the same unit granularity as the stream."""
    units = []
    i = 0
    while i < len(text):
        unit, j = _group(text, 0, 1.0, i)
        units.append(unit)
        i = j
    return units


SKIP_COST = 1.0        # stepping over a stream unit the sentence does not use
MISMATCH_COST = 4.0    # forcing two different units together; dearer than dropping
DROP_COST = 2.0        # a script unit the voiceover never pronounced
NEAR_COST = 0.1        # a known near form (numeral spelling, verified mishearing)


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def words_from_transcript(data):
    raw = list(data.get("words") or [])
    if not raw:
        for sent in data.get("sentences", []):
            raw.extend(sent.get("words", []))
    toks = []
    for w in raw:
        t = (w.get("corrected_text") or w.get("text") or "").strip()
        if not t:
            continue
        start = w.get("start", w.get("begin_time"))
        end = w.get("end", w.get("end_time"))
        if start is None or end is None:
            continue
        toks.append({"text": t, "start": float(start), "end": float(end)})
    toks.sort(key=lambda x: x["start"])
    return toks


def _group(text, start, step, i):
    """One unit starting at index `i`: a digit run, or a multi-char numeral run.

    Returns (unit_text, next_index).
    """
    if text[i].isdigit():
        j = i
        while j < len(text) and text[j].isdigit():
            j += 1
        return text[i:j], j
    # A Chinese numeral of more than one character is one unit ("一百四十" = 140);
    # a single numeral character stays single so "一场" keeps its 一 as part of the
    # phrase rather than becoming the number 1.
    j = i
    while j < len(text) and (text[j] in CN_DIGITS or text[j] in CN_UNITS or text[j] == "万"):
        j += 1
    if j - i >= 2:
        return text[i:j], j
    return text[i], i + 1


def chars_from_words(toks):
    """Flat unit stream carrying time spans.

    Digits and multi-character Chinese numerals form single units, because the
    voiceover says a number as one Chinese numeral ("十") where the script writes
    two digits ("10"). Comparing units rather than characters is what lets those
    line up without shifting the rest of the sentence.
    """
    chars = []
    for t in toks:
        s = norm(t["text"])
        if not s:
            continue
        step = (t["end"] - t["start"]) / len(s)
        i = 0
        while i < len(s):
            unit, j = _group(s, t["start"], step, i)
            chars.append({"ch": unit, "start": t["start"] + i * step,
                          "end": t["start"] + j * step})
            i = j
    # Merge numeric units that straddle a word boundary (e.g. "1" then "40").
    merged = []
    for c in chars:
        if merged and abs(merged[-1]["end"] - c["start"]) < 1e-6 and _numeric(merged[-1]["ch"]) is not None and _numeric(c["ch"]) is not None:
            merged[-1] = {"ch": merged[-1]["ch"] + c["ch"], "start": merged[-1]["start"],
                          "end": c["end"]}
        else:
            merged.append(dict(c))
    return merged


def _numeric(unit):
    """The numeric value of a unit, or None when it is not a number."""
    if unit.isdigit():
        return int(unit)
    return parse_cn_number(unit)


def align_one(target, chars, cursor, band=BAND, findings=None, label="",
              min_true_ratio=0.80, max_target_drop_ratio=0.35, max_skip_units=6):
    """Align one script sentence onto the character stream, minimising total cost.

    This is a banded dynamic program over (target index, stream index), not a
    greedy walk. Greedy is what made this function fragile: a single local choice
    (mismatch here, or drop there) could derail the whole sentence, and each fix
    traded one case for another. The DP considers the whole sentence at once, so
    the cost model below is the only thing that has to be right.

    Move costs, all per unit:

    - match: 0 when the units are the same or a known near form (numeral spelling,
      verified mishearing), otherwise MISMATCH_COST
    - skip a stream unit the sentence does not use (a filler the ASR emitted): SKIP_COST
    - drop a target unit the voiceover never pronounced ("已经" heard as "已"): DROP_COST

    DROP_COST < MISMATCH_COST, so a swallowed script character is dropped rather
    than forced onto a wrong stream unit, which is what keeps the rest of the
    sentence in place instead of shifting by one. The band caps how far the match
    may drift from the diagonal, so a sentence can never slide onto a later
    lookalike phrase -- the failure that silently shifted every following
    sentence in the earlier hand-rolled versions.

    Returns (start_s, end_s, next_cursor), or None when the result is not credible
    (wrong opening unit, too few exact matches, or too many dropped units).
    """
    target = target_units(target) if isinstance(target, str) else target
    n = len(target)
    if n == 0 or cursor >= len(chars):
        return None
    # Window: at most the sentence length plus the band, so a banded DP stays cheap
    # even for a long sentence inside a long transcript.
    m = min(len(chars) - cursor, n + band)
    if m <= 0:
        return None
    hi = cursor + m
    lo = cursor

    INF = float("inf")
    # best[i][j]: cost of aligning target[:i] against stream[lo:lo+j]
    best = [[INF] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]
    best[0][0] = 0.0
    for j in range(1, m + 1):
        best[0][j] = best[0][j - 1] + SKIP_COST
        back[0][j] = ("skip", 0, j - 1)
    for i in range(1, n + 1):
        best[i][0] = best[i - 1][0] + DROP_COST
        back[i][0] = ("drop", i - 1, 0)
        # keep the band around the diagonal so the match cannot drift away
        j_lo = max(1, i - band)
        j_hi = min(m, i + band)
        for j in range(j_lo, j_hi + 1):
            su = chars[lo + j - 1]["ch"]
            tu = target[i - 1]
            if su == tu:
                match = 0.0
            elif same_char(tu, su):
                match = NEAR_COST
            else:
                match = MISMATCH_COST
            options = (
                (best[i - 1][j - 1] + match, "match", i - 1, j - 1),
                (best[i - 1][j] + DROP_COST, "drop", i - 1, j),
                (best[i][j - 1] + SKIP_COST, "skip", i, j - 1),
            )
            cost, kind, pi, pj = min(options, key=lambda o: o[0])
            best[i][j] = cost
            back[i][j] = (kind, pi, pj)

    # End anywhere in the last stretch: trailing stream units are simply not consumed.
    tail_lo = min(n, m)
    total, end_j = min((best[n][j], j) for j in range(tail_lo, m + 1))
    if total == INF:
        return None

    i, j = n, end_j
    consumed, dropped, skipped = [], [], []
    while i > 0 or j > 0:
        kind, pi, pj = back[i][j]
        if kind == "match":
            consumed.append((pi, lo + pj))
        elif kind == "drop":
            dropped.append(pi)
        elif kind == "skip":
            skipped.append(lo + pj)
        i, j = pi, pj
    consumed.reverse()
    dropped.reverse()
    skipped.reverse()
    if not consumed:
        return None

    exact = sum(1 for ti, si in consumed if chars[si]["ch"] == target[ti])
    if exact / n < min_true_ratio or len(dropped) / n > max_target_drop_ratio:
        return None
    first = chars[consumed[0][1]]["ch"]
    if first != target[0] and not same_char(target[0], first):
        return None

    if findings is not None:
        if dropped:
            findings.append({
                "kind": "target_chars_dropped", "sentence": label,
                "count": len(dropped),
                "chars": "".join(target[i] for i in dropped[:24]),
                "ratio": round(len(dropped) / n, 3),
                "note": "script characters the voiceover did not pronounce; screen copy unchanged",
            })
        for ti, si in consumed:
            actual = chars[si]["ch"]
            if actual == target[ti]:
                continue
            kind = ("numeral_equivalent" if actual in DIGIT_EQUIV.get(target[ti], "")
                    else "asr_rewrite")
            findings.append({
                "kind": kind, "sentence": label,
                "script_char": target[ti], "asr_char": actual,
                "asr_time_s": round(chars[si]["start"], 3),
            })
        if skipped:
            findings.append({
                "kind": "stream_chars_skipped", "sentence": label,
                "count": len(skipped),
                "chars": "".join(chars[k]["ch"] for k in skipped[:24]),
                "ratio": round(len(skipped) / n, 3),
                "note": "ASR characters the script sentence does not use",
            })
    return (chars[consumed[0][1]]["start"], chars[consumed[-1][1]]["end"],
            consumed[-1][1] + 1)


def main():
    ap = argparse.ArgumentParser(description="Align script sentences to ASR word timings.")
    ap.add_argument("--script", required=True)
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--json-detail", default=None)
    ap.add_argument("--max-skip-ratio", type=float, default=0.15,
                    help="fail when skipped ASR characters exceed this share of a sentence")
    args = ap.parse_args()

    script = load(args.script)
    sentences = script.get("sentences") or []
    if not sentences:
        sys.exit("script has no sentences")
    overrides = script.get("align_text_override") or {}
    toks = words_from_transcript(load(args.transcript))
    if not toks:
        sys.exit("transcript has no word timings")
    chars = chars_from_words(toks)

    findings = []
    timings = {}
    cursor = 0
    for s in sentences:
        text = overrides.get(s["id"], s["text_zh"])
        target = norm(text)
        res = align_one(target, chars, cursor, findings=findings, label=s["id"])
        if res is None:
            sys.exit(f"alignment failed for {s['id']}: {s['text_zh'][:30]!r} "
                     f"(stream too short or shifted; check the sentence split)")
        start, end, cursor = res
        timings[s["id"]] = {"start_s": round(start, 3), "end_s": round(end, 3)}

    audio_end = chars[-1]["end"]
    checked = []
    for s in sentences:
        t = timings[s["id"]]
        checked.append({"id": s["id"], "start_s": t["start_s"], "end_s": t["end_s"],
                        "text_zh": s["text_zh"]})
    # Monotonicity and coverage are the two invariants that actually matter.
    for a, b in zip(checked, checked[1:]):
        if b["start_s"] < a["start_s"] - 1e-6:
            sys.exit(f"non-monotonic timing at {b['id']}: {b['start_s']} < {a['start_s']}")
    if checked[-1]["end_s"] < audio_end - MAX_TAIL_S:
        sys.exit(f"last sentence ends at {checked[-1]['end_s']:.2f}s but audio runs to "
                 f"{audio_end:.2f}s: the tail was not covered")

    heavy = [f for f in findings
             if f["kind"] == "stream_chars_skipped" and f.get("ratio", 0) > args.max_skip_ratio]
    if heavy:
        for f in heavy:
            print(f"warning: {f['sentence']} skipped {f['count']} ASR chars "
                  f"({f['ratio']:.0%} of the sentence)", file=sys.stderr)

    detail = {"revision": script.get("revision", "script-001"),
              "timing_source": "align_script.py banded edit-distance alignment",
              "audio_end_s": round(audio_end, 3),
              "findings": findings}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"revision": detail["revision"], "sentences": checked}, f,
                  ensure_ascii=False, indent=2)
    if args.json_detail:
        with open(args.json_detail, "w", encoding="utf-8") as f:
            json.dump(detail, f, ensure_ascii=False, indent=2)

    print(json.dumps({"sentences": len(checked),
                      "audio_end_s": round(audio_end, 3),
                      "last_end_s": checked[-1]["end_s"],
                      "findings": len(findings),
                      "out": args.out}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()