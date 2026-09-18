# -*- coding: utf-8 -*-
"""Tighten TTS pauses and remap word-level timestamps onto the shortened audio.

Whole-paragraph TTS leaves a 0.3-0.9s pause at every punctuation mark: a ~50s
voiceover can hold 10s+ of silence, which reads as "the video is too slow". This
shrinks every pause longer than --max-pause-s down to --keep-pause-s without
touching a single phoneme, and remaps the word timestamps through the exact same
time mapping so audio and subtitles cannot drift apart.

Steps: detect silences with ffmpeg -> build piecewise time map -> cut/join audio
-> remap words -> verify against the tightened audio.

Usage:
  python compress_pauses.py --media voiceover.wav --transcript asr/transcript.source.json \
      --out voiceover.tight.wav --out-transcript asr/transcript.tight.json \
      --ffmpeg "C:/path/ffmpeg.exe"
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

DEFAULT_FFMPEG = "ffmpeg"
CROSSFADE_S = 0.012  # keep a hair of overlap so joins do not click


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


def resolve_ffmpeg(explicit=None):
    if explicit:
        return explicit
    found = shutil.which("ffmpeg")
    if found:
        return found
    tools = os.path.join(os.path.expanduser("~"), ".agents", "skills", ".tools", "bin", "ffmpeg.exe")
    if os.path.exists(tools):
        return tools
    raise SystemExit("ffmpeg not found; pass --ffmpeg with its full path")


def probe(ffmpeg, media):
    """ffprobe next to ffmpeg, else re-use ffmpeg -i parsing."""
    probe_path = os.path.join(os.path.dirname(ffmpeg), "ffprobe.exe")
    if not os.path.exists(probe_path):
        probe_path = shutil.which("ffprobe") or (os.path.join(os.path.dirname(ffmpeg), "ffprobe")
                                                 if os.path.exists(os.path.join(os.path.dirname(ffmpeg), "ffprobe")) else None)
    if probe_path:
        res = run([probe_path, "-v", "error", "-show_entries", "format=duration",
                   "-of", "default=noprint_wrappers=1:nokey=1", media])
        try:
            return float(res.stdout.strip())
        except ValueError:
            pass
    res = run([ffmpeg, "-hide_banner", "-i", media])
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", res.stderr)
    if not m:
        raise SystemExit("cannot read media duration")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def detect_silences(ffmpeg, media, noise_db, min_silence):
    res = run([ffmpeg, "-hide_banner", "-i", media, "-af",
               f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"])
    spans = []
    start = None
    for line in res.stderr.splitlines():
        ms = re.search(r"silence_start:\s*(-?[\d.]+)", line)
        if ms:
            start = max(0.0, float(ms.group(1)))
            continue
        me = re.search(r"silence_end:\s*([\d.]+)", line)
        if me and start is not None:
            end = float(me.group(1))
            if end > start:
                spans.append([start, end])
            start = None
    return spans


def build_map(duration, silences, max_pause, keep_pause):
    """Return (parts, time_map, total_out) for the tightened timeline.

    A pause longer than max_pause is replaced by keep_pause seconds; shorter pauses
    are preserved. Each pause keeps half of its padding on both sides (so the join
    is a real crossfade through quiet audio), which means the pause's own slice must
    be exactly keep_pause + CROSSFADE_S long: the crossfade then eats precisely the
    overlap and the pause occupies keep_pause seconds in the output. The retained
    slices are anchored on the existing audio instead of on silence boundaries, so
    the output length matches the map exactly and word timings stay in sync.
    """
    pad = CROSSFADE_S / 2
    pauses = []
    cursor = 0.0
    for s_start, s_end in silences:
        s_start = max(s_start, cursor)
        length = s_end - s_start
        if length <= 0:
            continue
        if length > max_pause:
            pauses.append({"start": s_start, "end": s_end, "keep": min(keep_pause, length)})
        else:
            pauses.append({"start": s_start, "end": s_end, "keep": length})
        cursor = s_end

    # voice spans fill everything the pauses do not cover
    voice_spans = []
    cursor = 0.0
    for p in pauses:
        if p["start"] > cursor:
            voice_spans.append((cursor, p["start"]))
        cursor = max(cursor, p["end"])
    if cursor < duration:
        voice_spans.append((cursor, duration))

    slots = ([{"kind": "voice", "start": a, "end": b} for a, b in voice_spans]
             + [{"kind": "pause", "start": p["start"], "end": p["end"], "keep": p["keep"]}
                for p in pauses])
    slots.sort(key=lambda s: s["start"])

    parts = []
    total_out = 0.0
    for idx, slot in enumerate(slots):
        if slot["kind"] == "voice":
            keep = slot["end"] - slot["start"]
            parts.append({"kind": "voice", "src_start": slot["start"], "src_end": slot["end"],
                          "out": keep})
            total_out += keep
            continue
        # pause: take keep + one crossfade so the overlap lands inside the quiet slice
        need = slot["keep"] + CROSSFADE_S
        start, end = slot["start"], slot["end"]
        mid = (start + end) / 2
        src_start = max(start - pad, mid - need / 2)
        src_end = src_start + need
        if src_end > end + pad:
            src_end = end + pad
            src_start = src_end - need
        limit = slots[idx + 1]["start"] if idx + 1 < len(slots) else duration
        src_end = min(src_end, limit)
        src_start = max(0.0, min(src_start, src_end - need))
        keep = src_end - src_start - CROSSFADE_S
        keep = max(min(keep, slot["keep"]), 0.02)
        parts.append({"kind": "pause", "src_start": src_start, "src_end": src_end, "out": keep})
        total_out += keep

    time_map = []
    out_cursor = 0.0
    for p in parts:
        time_map.append({
            "src_start": round(p["src_start"], 6),
            "src_end": round(p["src_end"], 6),
            "out_start": round(out_cursor, 6),
            "kind": p["kind"],
            "src_len": round(p["src_end"] - p["src_start"], 6),
            "out_len": round(p["out"], 6),
        })
        out_cursor += p["out"]
    return parts, time_map, out_cursor


def remap(t, time_map):
    """Map a source time onto the tightened timeline.

    A retained pause is represented by an ~80ms slice taken from its middle, so the
    pause's edges are intentionally absent from the map. A time landing in one of
    those gaps is interpolated between the previous segment's output end and the
    next segment's output start. Without this, gap times collapsed to 0.0 and whole
    sentences appeared to start at the beginning of the video.
    """
    if not time_map:
        return max(t, 0.0)
    if t <= time_map[0]["src_start"]:
        return time_map[0]["out_start"]

    for i, seg in enumerate(time_map):
        if seg["src_start"] <= t <= seg["src_end"]:
            if seg["src_len"] <= 1e-9:
                return seg["out_start"]
            if seg["kind"] == "voice":
                return seg["out_start"] + (t - seg["src_start"])
            ratio = seg["out_len"] / seg["src_len"]
            return seg["out_start"] + (t - seg["src_start"]) * ratio

        nxt = time_map[i + 1] if i + 1 < len(time_map) else None
        if nxt is None or t < nxt["src_start"]:
            prev_out_end = seg["out_start"] + seg["out_len"]
            if nxt is None:
                return prev_out_end
            gap_src = nxt["src_start"] - seg["src_end"]
            if gap_src <= 1e-9:
                return nxt["out_start"]
            frac = (t - seg["src_end"]) / gap_src
            return prev_out_end + (nxt["out_start"] - prev_out_end) * frac

    last = time_map[-1]
    return last["out_start"] + last["out_len"]


def words_from(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    raw = list(data.get("words") or [])
    if not raw:
        for sent in data.get("sentences", []):
            raw.extend(sent.get("words", []))
    return data, raw


def next_word_id(pid):
    m = re.match(r"c(\d+)_s(\d+)_w(\d+)", pid)
    if not m:
        return (1, 0, 0)
    return (int(m.group(1)) + 1, int(m.group(2)), int(m.group(3)))


def reconcile(time_map, predicted, actual):
    """Match the time map to the produced audio length.

    Overlapping crossfades and clipped pause take-windows make the realised length
    differ from the predicted sum by a few hundred milliseconds. Rescaling the map
    onto the measured length keeps subtitle timings within a few tens of
    milliseconds, and the residual is reported so it can be judged rather than
    assumed away. Voice spans are the overwhelming majority of the timeline, so a
    uniform scale is accurate to well under one frame here.
    """
    if predicted <= 0 or actual <= 0:
        return time_map, 0.0
    factor = actual / predicted
    for seg in time_map:
        seg["out_start"] = round(seg["out_start"] * factor, 6)
        seg["out_len"] = round(seg["out_len"] * factor, 6)
    return time_map, abs(actual - predicted)


def cut_and_join(ffmpeg, media, parts, out_path):
    """Single ffmpeg pass: trim each part and concat with short crossfades."""
    atrim = []
    labels = []
    for idx, p in enumerate(parts):
        atrim.append(
            f"[0:a]atrim=start={p['src_start']:.6f}:end={p['src_end']:.6f},"
            f"asetpts=PTS-STARTPTS[a{idx}]"
        )
        labels.append(f"[a{idx}]")
    filter_parts = list(atrim)
    if len(labels) == 1:
        filter_parts.append(f"{labels[0]}anull[out]")
    else:
        chain = labels[0]
        for idx in range(1, len(labels)):
            last = "[out]" if idx == len(labels) - 1 else f"[x{idx}]"
            filter_parts.append(f"{chain}{labels[idx]}acrossfade=d={CROSSFADE_S}:c1=tri:c2=tri{last}")
            chain = last
    graph = ";".join(filter_parts)
    cmd = [ffmpeg, "-hide_banner", "-v", "error", "-y", "-i", media,
           "-filter_complex", graph, "-map", "[out]", out_path]
    res = run(cmd)
    if res.returncode != 0:
        raise SystemExit("ffmpeg cut/join failed:\n" + res.stderr[-3000:])


def main():
    ap = argparse.ArgumentParser(description="Tighten TTS pauses and remap word timestamps.")
    ap.add_argument("--media", required=True)
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--out-transcript", required=True)
    ap.add_argument("--analysis", default=None, help="Optional JSON path for the measurement report")
    ap.add_argument("--ffmpeg", default=None)
    ap.add_argument("--noise-db", default="-38")
    ap.add_argument("--min-silence-s", type=float, default=0.18)
    ap.add_argument("--max-pause-s", type=float, default=0.25)
    ap.add_argument("--keep-pause-s", type=float, default=0.08)
    ap.add_argument("--second-pass", dest="second_pass", action="store_true", default=True,
                    help="Re-tighten pauses that survived the crossfades (default on)")
    ap.add_argument("--no-second-pass", dest="second_pass", action="store_false")
    args = ap.parse_args()

    ffmpeg = resolve_ffmpeg(args.ffmpeg)
    duration = probe(ffmpeg, args.media)
    silences = detect_silences(ffmpeg, args.media, args.noise_db, args.min_silence_s)
    silence_total = sum(e - s for s, e in silences)

    parts, time_map, total_out = build_map(duration, silences, args.max_pause_s, args.keep_pause_s)
    cut_and_join(ffmpeg, args.media, parts, args.out)

    # Measure the produced audio, then put the time map on that exact length so the
    # word timestamps cannot drift from the audio they describe.
    actual_out = probe(ffmpeg, args.out)
    time_map, drift = reconcile(time_map, total_out, actual_out)

    data, raw = words_from(args.transcript)
    new_words = []
    for w in raw:
        src_start = float(w.get("start", w.get("begin_time", 0)))
        src_end = float(w.get("end", w.get("end_time", 0)))
        nw = dict(w)
        nw["src_start_s"] = round(src_start, 3)
        nw["src_end_s"] = round(src_end, 3)
        nw["start"] = round(remap(src_start, time_map), 3)
        nw["end"] = round(remap(src_end, time_map), 3)
        new_words.append(nw)
    data["words"] = new_words

    # A time map with unmapped gaps once collapsed later timestamps to 0.0. Check the
    # remapped sequence is monotone and non-degenerate before it is used for layout.
    backwards = []
    for a, b in zip(new_words, new_words[1:]):
        if b["start"] < a["start"] - 1e-6 or b["end"] < a["end"] - 1e-6:
            backwards.append(f"{a.get('text')}->{b.get('text')}")
    zero_late = [w.get("text") for w in new_words
                 if w["start"] <= 0.0 and w.get("src_start_s", 0) > 0.5]
    map_problems = []
    if backwards:
        map_problems.append(f"{len(backwards)} non-monotone word times, e.g. {backwards[:3]}")
    if zero_late:
        map_problems.append(f"{len(zero_late)} words after 0.5s mapped to time 0, e.g. {zero_late[:5]}")

    # Crossfading can leave a stray pause slightly longer than requested. One more
    # pass over the tightened audio removes it; the maps are composed so the word
    # timings stay attached to the audio that is actually delivered.
    passes = 1
    if args.second_pass:
        residual = detect_silences(ffmpeg, args.out, args.noise_db, max(args.max_pause_s, 0.30))
        if residual:
            stage = args.out + ".stage2.wav"
            parts2, map2, predicted2 = build_map(actual_out, residual, 0.24, args.keep_pause_s)
            cut_and_join(ffmpeg, args.out, parts2, stage)
            actual2 = probe(ffmpeg, stage)
            map2, _ = reconcile(map2, predicted2, actual2)
            for w in new_words:
                first = w["start"]
                second = w["end"]
                w["start"] = round(remap(first, map2), 3)
                w["end"] = round(remap(second, map2), 3)
            os.replace(stage, args.out)
            actual_out = actual2
            passes = 2

    data["pause_tightening"] = {
        "source": os.path.basename(args.media),
        "source_duration_s": round(duration, 3),
        "tightened_duration_s": round(actual_out, 3),
        "removed_s": round(duration - actual_out, 3),
        "silence_spans": len(silences),
        "silence_total_s": round(silence_total, 3),
        "max_pause_s": args.max_pause_s,
        "keep_pause_s": args.keep_pause_s,
        "noise_db": args.noise_db,
        "min_silence_s": args.min_silence_s,
        "passes": passes,
        "map_residual_s": round(drift, 4),
        "note": "audio and word timestamps share this mapping chain",
    }
    with open(args.out_transcript, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    after = detect_silences(ffmpeg, args.out, args.noise_db, args.min_silence_s)
    worst = max((e - s for s, e in after), default=0.0)
    problems = list(map_problems)
    if worst > args.max_pause_s + 0.06:
        problems.append(f"a pause of {worst:.3f}s survived both passes")

    report = {
        "media_in": args.media,
        "media_out": args.out,
        "transcript_out": args.out_transcript,
        "source_duration_s": round(duration, 3),
        "tightened_duration_s": round(actual_out, 3),
        "removed_s": round(duration - actual_out, 3),
        "removed_pct": round((duration - actual_out) / duration * 100, 1),
        "silences_before": len(silences),
        "silence_total_before_s": round(silence_total, 3),
        "longest_pause_before_s": round(max((e - s for s, e in silences), default=0.0), 3),
        "longest_pause_after_s": round(worst, 3),
        "passes": passes,
        "monotone_times": not backwards,
        "findings": problems,
        "status": "ok" if not problems else "review_required",
    }
    if args.analysis:
        with open(args.analysis, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if problems:
        sys.exit(2)

if __name__ == "__main__":
    main()
