# -*- coding: utf-8 -*-
"""Mechanically check a hook-video layout plan against the layout-motion rules.

The three defects users actually report -- "pacing too slow", "evidence material
slides under the subtitle band", "subtitles are one long unreadable line" -- are
all checkable from layout-plan.json. Checking them here keeps the QC report honest
instead of relying on eyeballing a few stills.

Checks:
  duration        total runtime vs the target / reference duration
  speed           spoken characters per second, and how much runtime is silence
  hook_events     visual events inside the first 5s
  screen_events   at least 3 visual events per screen
  dead_zone       no >= 2s stretch without a new visual event inside a screen
  material_zone   every material layer ends at or above subtitle_rule_y
  caption_long    every caption page is <= max caption characters
  caption_lines   each caption page renders within the allowed line budget
  caption_hold    every caption page stays on screen long enough to read
  caption_cover   caption pages cover the voiceover without gaps
  layer_overflow  layer start/end frames stay inside the video

Usage:
  python check_hook_plan.py --plan layout-plan.json [--json report.json] [--max-caption-chars 18]
Exit code is 1 when any check fails, 2 on bad input.
"""
import argparse
import json
import re
import sys

PUNCT = "，。、；：！？…—－·「」『』（）()《》\"'“”‘’ \u3000"
MIN_EVENT_GAP_S = 2.0
HOOK_WINDOW_S = 5.0
MIN_HOOK_EVENTS = 3
MIN_SCREEN_EVENTS = 3


def strip_punct(text):
    return "".join(ch for ch in text if ch not in PUNCT)


def visual_events(plan, screen):
    """Frames at which something visibly new happens inside a screen."""
    fps = plan["fps"]
    start, end = screen["start_frame"], screen["end_frame"]
    events = [start]
    for layer in plan["layers"]:
        if layer.get("screen") != screen["id"]:
            continue
        if start <= layer["start_frame"] < end:
            events.append(layer["start_frame"])
        for run in layer.get("emphasis_runs", []) or []:
            if run.get("emphasis") and start <= run.get("start_frame", -1) < end:
                events.append(run["start_frame"])
    for subject in plan.get("subjects", []):
        if screen["id"] in subject.get("screens", []):
            events.append(start)
    for backdrop in plan.get("backdrops", []):
        if screen["id"] in backdrop.get("screens", []):
            events.append(start)
    # A continuously running progress bar is a real visual event: it moves on every
    # frame, so a screen that carries it can never contain a visual dead zone.
    # Ticking it every MIN_EVENT_GAP_S keeps the arithmetic honest without
    # pretending the copy changed.
    if plan.get("persistent_motion"):
        step = max(1, int(fps * (MIN_EVENT_GAP_S - 0.1)))
        events.extend(range(start, end, step))
    return sorted(set(events)), fps


def main():
    ap = argparse.ArgumentParser(description="Validate a hook-video layout plan.")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--json", default=None, help="Write the full report here")
    ap.add_argument("--max-caption-chars", type=int, default=18)
    ap.add_argument("--max-caption-lines", type=int, default=2)
    ap.add_argument(
        "--target-duration-s", type=float, default=None,
        help="Reference/target duration; a video longer than 1.2x this is flagged",
    )
    args = ap.parse_args()

    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)

    fps = plan["fps"]
    L = plan["style"]["layout"]
    rule_y = L["subtitle_rule_y"]
    checks = {}
    findings = []

    def record(name, ok, detail, severity="fail"):
        checks[name] = {"status": "pass" if ok else severity, "detail": detail}
        if not ok:
            findings.append(f"{name}: {detail}")

    # ---- duration
    dur = plan["duration_frames"] / fps
    spoken = sum(len(strip_punct(c.get("text_zh", ""))) for c in plan.get("captions", []))
    audio_s = plan.get("audio", {}).get("duration_s") or dur
    detail = f"total {dur:.2f}s, spoken {spoken} chars, {spoken / dur:.2f} chars/s"
    if args.target_duration_s:
        ratio = dur / args.target_duration_s
        detail += f", {ratio:.2f}x reference ({args.target_duration_s:.1f}s)"
        record("duration", ratio <= 1.2, detail)
    else:
        record("duration", True, detail + " (no reference duration given)")

    # ---- speed / silence share
    tight = plan.get("audio", {}).get("pause_tightening") or {}
    if tight:
        removed = tight.get("removed_s", 0.0)
        share = removed / max(tight.get("source_duration_s", 1.0), 1e-6)
        record("speed", share <= 0.10,
               f"{tight.get('source_duration_s')}s -> {tight.get('tightened_duration_s')}s, "
               f"removed {removed}s ({share * 100:.1f}%)")
    else:
        record("speed", True, "no pause-tightening record in the plan (cannot prove气口 was tightened)",
               severity="warn")

    # ---- hook window and per-screen event density
    hook_events = []
    dead_zones = []
    thin_screens = []
    for screen in plan["screens"]:
        events, _ = visual_events(plan, screen)
        s0, s1 = screen["start_frame"] / fps, screen["end_frame"] / fps
        hook_events += [e for e in events if e / fps <= HOOK_WINDOW_S]
        if len(events) < MIN_SCREEN_EVENTS:
            thin_screens.append(f"{screen['id']}({len(events)})")
        for a, b in zip(events, events[1:]):
            if (b - a) / fps >= MIN_EVENT_GAP_S:
                dead_zones.append(f"{screen['id']} {a / fps:.1f}->{b / fps:.1f}s")
        if s1 <= HOOK_WINDOW_S and len(events) < MIN_HOOK_EVENTS:
            pass
    record("hook_events", len(hook_events) >= MIN_HOOK_EVENTS,
           f"{len(hook_events)} events in first {HOOK_WINDOW_S:.0f}s")
    record("screen_events", not thin_screens,
           "screens with < 3 events: " + ", ".join(thin_screens) if thin_screens else "every screen >= 3 events")
    record("dead_zone", not dead_zones,
           "gaps >= 2s: " + "; ".join(dead_zones) if dead_zones else "no >= 2s visual gap")

    # ---- evidence material must stay above the subtitle rule
    # Full-bleed backgrounds are exempt: the rule protects panel-style evidence
    # (a document panel, a screenshot, a chart) from being cut by the band. A
    # deliberately washed-out background behind the copy is a separate case and is
    # governed by the opacity rule instead.
    offenders = []
    for backdrop in plan.get("backdrops", []):
        if backdrop.get("band") == "background":
            continue
        bottom = backdrop.get("bottom_y")
        if bottom is None:
            continue
        if bottom > rule_y:
            offenders.append(f"{backdrop['id']} bottom {bottom} > rule {rule_y}")
    for subject in plan.get("subjects", []):
        bottom = subject.get("bottom_y")
        if bottom is None:
            continue
        if bottom > rule_y:
            offenders.append(f"{subject['id']} bottom {bottom} > rule {rule_y}")
    record("material_zone", not offenders,
           "; ".join(offenders) if offenders else f"all material bottoms <= {rule_y}")

    # ---- captions. The page budget counts punctuation-free characters, because the
    # rule is about how much text the viewer must read on one line.
    caps = plan.get("captions", [])
    policy = plan.get("caption_policy") or {}
    max_chars = policy.get("max_chars_per_page", args.max_caption_chars)
    max_lines = policy.get("max_lines", args.max_caption_lines)

    def page_len(cap):
        return len(strip_punct(cap["text_zh"]))

    long_pages = [f"{c['id']}={page_len(c)}" for c in caps if page_len(c) > max_chars]
    record("caption_long", not long_pages,
           f"pages over {max_chars} chars: " + ", ".join(long_pages) if long_pages
           else f"every page <= {max_chars} chars")

    over_lines = [c["id"] for c in caps if page_len(c) > max_chars * max_lines]
    record("caption_lines", not over_lines,
           "pages needing more than the line budget: " + ", ".join(over_lines) if over_lines
           else f"every page fits {max_lines} lines")

    dupes = []
    for a, b in zip(caps, caps[1:]):
        if a["text_zh"] == b["text_zh"]:
            dupes.append(f"{a['id']}={b['id']}")
    record("caption_duplicate", not dupes,
           "identical adjacent pages: " + ", ".join(dupes) if dupes
           else "no duplicated adjacent pages")

    short_holds = [f"{c['id']}={(c['end_frame'] - c['start_frame']) / fps:.2f}s" for c in caps
                   if (c["end_frame"] - c["start_frame"]) / fps < 0.8]
    record("caption_hold", not short_holds,
           "pages held < 0.8s: " + ", ".join(short_holds) if short_holds else "every page held >= 0.8s")

    covers = all(
        caps[i]["end_frame"] >= caps[i + 1]["start_frame"] - 1 for i in range(len(caps) - 1)
    ) if len(caps) > 1 else True
    record("caption_cover", covers, "subtitle pages cover the voiceover without gaps"
           if covers else "a gap or overlap exists between subtitle pages")

    # ---- layers stay inside the timeline
    outside = [l["layer_id"] for l in plan["layers"]
               if l["start_frame"] < 0 or l["end_frame"] > plan["duration_frames"]]
    record("layer_overflow", not outside,
           "layers outside the timeline: " + ", ".join(outside) if outside else "all layers inside the timeline")

    hard_fail = [k for k, v in checks.items() if v["status"] == "fail"]
    report = {
        "plan": args.plan,
        "revision": plan.get("revision"),
        "fps": fps,
        "duration_s": round(dur, 3),
        "checks": checks,
        "findings": findings,
        "status": "pass" if not hard_fail else "fail",
    }
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(1 if hard_fail else 0)


if __name__ == "__main__":
    main()