"""
build_report.py — Clean raw data and emit report_data.json for The Cart newsletter report.
Run from repo root: python3 src/build_report.py
"""

import csv
import json
import math
import re
import unicodedata
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

RAW = Path("data/raw")
OUT = Path("report_data.json")

NULL_TOKENS = {"", "na", "n/a", "null", "none", "-", "#n/a"}


# ── helpers ──────────────────────────────────────────────────────────────────

def is_null(v):
    return str(v).strip().lower() in NULL_TOKENS


def parse_number(v):
    """Parse integers/floats with commas, k-suffix, $, USD, % stripped."""
    if is_null(v):
        return None
    s = str(v).strip()
    s = s.replace(",", "").replace("$", "").replace("USD", "").strip()
    if s.lower().endswith("k"):
        try:
            return float(s[:-1]) * 1000
        except ValueError:
            return None
    if s.endswith("%"):
        try:
            return float(s[:-1])
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_date(v):
    """Parse mixed date formats to a date object. Returns None on failure."""
    if is_null(v):
        return None
    s = str(v).strip()

    # ISO week: 2024-W09
    m = re.match(r"^(\d{4})-W(\d{1,2})$", s)
    if m:
        return datetime.strptime(f"{m.group(1)}-W{int(m.group(2)):02d}-1", "%Y-W%W-%w").date()

    fmts = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y",
        "%b %d, %Y",
        "%d-%b-%y",
        "%Y-%m-%dT%H:%M:%S",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def parse_duration_seconds(v):
    """Convert time_on_section to seconds. Returns None if unparseable or ≤0."""
    if is_null(v):
        return None
    s = str(v).strip()

    # HH:MM:SS or MM:SS
    if ":" in s:
        parts = s.split(":")
        try:
            parts = [float(p) for p in parts]
            if len(parts) == 3:
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
            if len(parts) == 2:
                return parts[0] * 60 + parts[1]
        except ValueError:
            return None

    # Xm Ys  e.g. "3m 37s"
    m = re.match(r"^(\d+(?:\.\d+)?)\s*m\s*(\d+(?:\.\d+)?)\s*s$", s, re.I)
    if m:
        return float(m.group(1)) * 60 + float(m.group(2))

    # X min  e.g. "1.2 min"
    m = re.match(r"^(\d+(?:\.\d+)?)\s*min$", s, re.I)
    if m:
        return float(m.group(1)) * 60

    # plain seconds
    try:
        val = float(s)
        return val if val > 0 else None
    except ValueError:
        return None


def normalize_device(v):
    if is_null(v):
        return None
    s = str(v).strip().lower()
    mobile_tokens = {"iphone", "android", "mobile", "phone"}
    desktop_tokens = {"web", "desktop", "pc"}
    tablet_tokens = {"ipad", "tablet"}
    app_tokens = {"app", "mobile app", "android app", "ios app"}
    if s in mobile_tokens:
        return "mobile"
    if s in desktop_tokens:
        return "desktop"
    if s in tablet_tokens:
        return "tablet"
    if s in app_tokens:
        return "app"
    return None


# Canonical section mapping — order matters: longer/more-specific patterns first
CANONICAL_SECTIONS = [
    "Deals of the Week",
    "New Arrivals",
    "Editor's Picks",
    "Tech & Gadgets",
    "Home & Living",
    "Sponsored Spotlight",
    "Reader Q&A",
]

# Pre-normalized (lower, stripped, punct-collapsed) → canonical
_SECTION_MAP = {}


def _add(raw_variants, canonical):
    for v in raw_variants:
        _SECTION_MAP[v] = canonical


_add(
    [
        "deals of the week", "deals of the wek", "deals", "dotw",
    ],
    "Deals of the Week",
)
_add(
    [
        "new arrivals", "newarrivals", "new_arrivals",
    ],
    "New Arrivals",
)
_add(
    [
        "editor's picks", "editors picks", "editors' picks", "editor picks",
        "editors pick",
    ],
    "Editor's Picks",
)
_add(
    [
        "tech & gadgets", "tech and gadgets", "tech gadgets", "tech/gadgets",
        "tech & gadgets", "techgadgets",
    ],
    "Tech & Gadgets",
)
_add(
    [
        "home & living", "home and living", "home living", "homeliving",
        "home & living", "home&living",
    ],
    "Home & Living",
)
_add(
    [
        "sponsored spotlight", "sponsor spotlight", "sponsored",
        "sponsoredspotlight",
    ],
    "Sponsored Spotlight",
)
_add(
    [
        "reader q&a", "reader q & a", "reader qanda", "q&a", "reader qa",
        "reader q and a",
    ],
    "Reader Q&A",
)


def _norm_section_key(v):
    """Lower, strip, collapse whitespace, remove most punctuation for lookup."""
    s = unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode()
    s = s.lower().strip()
    s = re.sub(r"[\s_]+", " ", s)
    s = re.sub(r"['\"]", "'", s)
    # remove trailing/leading punctuation but keep & / inside
    s = s.strip(" .,;:")
    return s


def normalize_section(v):
    if is_null(v):
        return "Other (review)"
    key = _norm_section_key(v)
    if key in _SECTION_MAP:
        return _SECTION_MAP[key]
    # fuzzy: remove spaces/punctuation and retry
    bare = re.sub(r"[^a-z0-9]", "", key)
    for map_key, canonical in _SECTION_MAP.items():
        if re.sub(r"[^a-z0-9]", "", map_key) == bare:
            return canonical
    return "Other (review)"


_SPONSOR_MAP = {}


def _add_sponsor(raw_variants, canonical):
    for v in raw_variants:
        _SPONSOR_MAP[re.sub(r"[^a-z0-9]", "", v.lower())] = canonical


_add_sponsor(
    ["Bright Home", "BRIGHTHOME", "Bright-Home", "BrightHome", "brighthome", "bright home"],
    "BrightHome",
)
_add_sponsor(
    ["North Peak Outdoors", "NorthPeak", "northpeak outdoors", "NorthPeak Outdoors",
     "north peak outdoors"],
    "North Peak Outdoors",
)
_add_sponsor(
    ["Volt Elec.", "volt electronics", "VOLT Electronics", "Volt Electronics",
     "volt elec"],
    "Volt Electronics",
)
_add_sponsor(
    ["ACME", "acme supplies", "Acme Supplies", "Acme Supplies Inc", "acme"],
    "ACME Supplies",
)
_add_sponsor(
    ["pure wellness co", "PureWellness Co.", "Pure Wellness Co", "Pure Wellness",
     "pure wellness"],
    "Pure Wellness Co.",
)


def normalize_sponsor(v):
    if not v:
        return v
    key = re.sub(r"[^a-z0-9]", "", v.lower())
    return _SPONSOR_MAP.get(key, v)


def normalize_issue_id(v):
    if is_null(v):
        return None
    s = str(v).strip()
    # ISS1027 → ISS-1027
    m = re.match(r"^ISS-?(\d+)$", s, re.I)
    if m:
        return f"ISS-{m.group(1)}"
    return None


def fmt_seconds(secs):
    """Format seconds as '1m 35s' for display."""
    if secs is None:
        return "N/A"
    m = int(secs) // 60
    s = int(secs) % 60
    if m == 0:
        return f"{s}s"
    return f"{m}m {s}s"


def median(vals):
    s = sorted(v for v in vals if v is not None)
    if not s:
        return None
    n = len(s)
    mid = n // 2
    return (s[mid - 1] + s[mid]) / 2 if n % 2 == 0 else s[mid]


def rolling_avg(series, window=4):
    result = []
    for i in range(len(series)):
        window_vals = [v for v in series[max(0, i - window + 1): i + 1] if v is not None]
        result.append(round(sum(window_vals) / len(window_vals), 1) if window_vals else None)
    return result


def week_start(d):
    """Return the Monday of the week containing date d."""
    return d - timedelta(days=d.weekday())


# ── 1. Clean newsletter_sends_raw.csv ────────────────────────────────────────

def clean_sends():
    path = RAW / "newsletter_sends_raw.csv"
    with open(path) as f:
        rows = list(csv.DictReader(f))

    raw_count = len(rows)
    print(f"\n── SENDS ──")
    print(f"  Rows in: {raw_count}")

    # Drop rows with null issue_id
    rows = [r for r in rows if not is_null(r.get("issue_id", ""))]
    print(f"  After dropping blank issue_id: {len(rows)}")

    # Normalize issue_id
    for r in rows:
        r["issue_id"] = normalize_issue_id(r["issue_id"])
    rows = [r for r in rows if r["issue_id"]]

    # Deduplicate: keep row with most non-null fields
    by_id = {}
    for r in rows:
        iid = r["issue_id"]
        if iid not in by_id:
            by_id[iid] = r
        else:
            existing_nulls = sum(1 for v in by_id[iid].values() if is_null(v))
            new_nulls = sum(1 for v in r.values() if is_null(v))
            if new_nulls < existing_nulls:
                by_id[iid] = r
    rows = list(by_id.values())
    print(f"  After dedup: {len(rows)}")

    cleaned = []
    for r in rows:
        send_date = parse_date(r.get("send_date", ""))
        if send_date is None:
            continue  # can't place issue in time without a date

        recipients_raw = r.get("recipients", "")
        recipients = parse_number(recipients_raw)
        if recipients:
            recipients = int(recipients)

        opens_raw = r.get("opens", "").strip()
        if opens_raw.endswith("%"):
            pct = parse_number(opens_raw)
            opens = int(recipients * pct / 100) if (pct is not None and recipients) else None
        else:
            v = parse_number(opens_raw)
            opens = int(v) if v is not None else None

        unique_opens_raw = r.get("unique_opens", "")
        v = parse_number(unique_opens_raw)
        unique_opens = int(v) if v is not None else None

        clicks_raw = r.get("clicks", "")
        v = parse_number(clicks_raw)
        clicks = int(v) if v is not None else None

        cleaned.append({
            "issue_id": r["issue_id"],
            "send_date": send_date,
            "subject_line": r.get("subject_line", "").strip() or None,
            "recipients": recipients,
            "opens": opens,
            "unique_opens": unique_opens,
            "clicks": clicks,
        })

    dropped = raw_count - len(cleaned)
    print(f"  Rows out: {len(cleaned)}  (dropped {dropped})")
    return cleaned


# ── 2. Clean subscribers_weekly_raw.csv ──────────────────────────────────────

def clean_subscribers():
    path = RAW / "subscribers_weekly_raw.csv"
    with open(path) as f:
        rows = list(csv.DictReader(f))

    raw_count = len(rows)
    print(f"\n── SUBSCRIBERS ──")
    print(f"  Rows in: {raw_count}")

    cleaned = []
    for r in rows:
        week_raw = r.get("week", "")
        week = parse_date(week_raw)
        if week is None:
            continue
        week = week_start(week)  # normalize to Monday

        ar = parse_number(r.get("active_readers", ""))
        ns = parse_number(r.get("new_subs", ""))
        us = parse_number(r.get("unsubscribes", ""))

        churn_raw = r.get("churn_pct", "").strip().rstrip("%").strip()
        churn = parse_number(churn_raw)

        cleaned.append({
            "week": week,
            "active_readers": int(ar) if ar is not None else None,
            "new_subs": int(ns) if ns is not None else None,
            "unsubscribes": int(us) if us is not None else None,
            "churn_pct": round(churn, 4) if churn is not None else None,
        })

    # Deduplicate by week — keep row with most non-nulls
    by_week = {}
    for r in cleaned:
        w = r["week"]
        if w not in by_week:
            by_week[w] = r
        else:
            existing_nulls = sum(1 for v in by_week[w].values() if v is None)
            new_nulls = sum(1 for v in r.values() if v is None)
            if new_nulls < existing_nulls:
                by_week[w] = r
    cleaned = sorted(by_week.values(), key=lambda r: r["week"])

    dropped = raw_count - len(cleaned)
    print(f"  Rows out: {len(cleaned)}  (dropped {dropped})")
    return cleaned


# ── 3. Clean section_engagement_raw.csv ──────────────────────────────────────

def clean_engagement():
    path = RAW / "section_engagement_raw.csv"
    with open(path) as f:
        rows = list(csv.DictReader(f))

    raw_count = len(rows)
    print(f"\n── ENGAGEMENT ──")
    print(f"  Rows in: {raw_count}")

    # Dedup by event_id
    seen_events = {}
    for r in rows:
        eid = r.get("event_id", "").strip()
        if not eid or is_null(eid):
            continue
        if eid not in seen_events:
            seen_events[eid] = r
    rows = list(seen_events.values())
    print(f"  After event_id dedup: {len(rows)}")

    bot_count = 0
    other_count = 0
    cleaned = []

    for r in rows:
        issue_id = normalize_issue_id(r.get("issueID", ""))
        if issue_id is None:
            continue

        reader_id = r.get("reader_id", "").strip() or None
        section = normalize_section(r.get("section", ""))
        device = normalize_device(r.get("device", ""))

        ts_raw = r.get("timestamp", "")
        ts = parse_date(ts_raw)

        secs = parse_duration_seconds(r.get("time_on_section", ""))
        if secs is not None and secs > 1800:
            bot_count += 1
            secs = None  # exclude from time metrics but keep the event
        if secs is not None and secs <= 0:
            secs = None

        if section == "Other (review)":
            other_count += 1

        cleaned.append({
            "event_id": r["event_id"].strip(),
            "issue_id": issue_id,
            "reader_id": reader_id,
            "section": section,
            "time_on_section": secs,
            "device": device,
            "date": ts,
        })

    dropped = raw_count - len(cleaned)
    print(f"  Rows out: {len(cleaned)}  (dropped {dropped})")
    print(f"  Bot sessions (time >1800s) excluded from time metrics: {bot_count}")
    print(f"  Events in 'Other (review)': {other_count}")
    return cleaned, bot_count, other_count


# ── 4. Clean sponsors_raw.csv ────────────────────────────────────────────────

def clean_sponsors():
    path = RAW / "sponsors_raw.csv"
    with open(path) as f:
        rows = list(csv.DictReader(f))

    raw_count = len(rows)
    print(f"\n── SPONSORS ──")
    print(f"  Rows in: {raw_count}")

    cleaned = []
    for r in rows:
        pid = r.get("placement_id", "").strip()
        sponsor = normalize_sponsor(r.get("sponsor_name", "").strip() or None)

        issue_raw = r.get("issue", "").strip()
        issue_id = normalize_issue_id(issue_raw)

        spend_raw = r.get("spend", "")
        spend = parse_number(spend_raw)

        imp_raw = r.get("impressions", "")
        imp = parse_number(imp_raw)

        section = normalize_section(r.get("section_placed", ""))

        cleaned.append({
            "placement_id": pid,
            "sponsor_name": sponsor,
            "issue_id": issue_id,
            "section": section,
            "spend": round(spend, 2) if spend is not None else None,
            "impressions": int(imp) if imp is not None else None,
        })

    dropped = raw_count - len(cleaned)
    print(f"  Rows out: {len(cleaned)}  (dropped {dropped})")
    return cleaned


# ── 5. Compute metrics ────────────────────────────────────────────────────────

def compute_metrics(sends, subscribers, engagement, sponsors,
                    bot_count, other_count):

    # --- KPIs ---
    subs_sorted = sorted(subscribers, key=lambda r: r["week"])
    latest_sub = subs_sorted[-1] if subs_sorted else {}
    latest_ar = latest_sub.get("active_readers")

    # 4-week average active readers (latest 4 data points)
    recent_ar = [r["active_readers"] for r in subs_sorted[-4:] if r["active_readers"] is not None]
    avg_4w = round(sum(recent_ar) / len(recent_ar)) if recent_ar else None

    # Growth from first to latest period
    first_ar = subs_sorted[0].get("active_readers") if subs_sorted else None
    if first_ar and latest_ar:
        growth_pct = round((latest_ar - first_ar) / first_ar * 100, 1)
    else:
        growth_pct = None

    total_sponsor_spend = sum(s["spend"] for s in sponsors if s["spend"] is not None)

    # Average open rate across sends
    open_rates = []
    for s in sends:
        if s["recipients"] and s["opens"]:
            open_rates.append(s["opens"] / s["recipients"] * 100)
    avg_open_rate = round(sum(open_rates) / len(open_rates), 1) if open_rates else None

    kpis = {
        "latest_active_readers": latest_ar,
        "latest_week": str(latest_sub.get("week", "")),
        "avg_4w_readers": avg_4w,
        "growth_pct": growth_pct,
        "total_sponsor_spend": round(total_sponsor_spend, 2),
        "avg_open_rate": avg_open_rate,
        "reporting_start": str(subs_sorted[0]["week"]) if subs_sorted else "",
        "reporting_end": str(subs_sorted[-1]["week"]) if subs_sorted else "",
    }

    # --- Weekly readers ---
    weeks_data = [
        {
            "week": str(r["week"]),
            "active_readers": r["active_readers"],
        }
        for r in subs_sorted
    ]
    ar_series = [r["active_readers"] for r in subs_sorted]
    rolling = rolling_avg(ar_series, 4)
    for i, r in enumerate(weeks_data):
        r["rolling_4w"] = rolling[i]

    # --- Section time (median seconds, event count) ---
    section_times = {}  # section → list of valid seconds
    for ev in engagement:
        if ev["time_on_section"] is not None:
            section_times.setdefault(ev["section"], []).append(ev["time_on_section"])

    section_time_data = []
    for section in CANONICAL_SECTIONS + ["Other (review)"]:
        times = section_times.get(section, [])
        med = median(times)
        section_time_data.append({
            "section": section,
            "median_seconds": round(med, 1) if med is not None else None,
            "median_fmt": fmt_seconds(med),
            "event_count": len(times),
        })
    section_time_data = [d for d in section_time_data if d["median_seconds"] is not None]
    section_time_data.sort(key=lambda d: d["median_seconds"], reverse=True)

    # --- Section popularity ---
    # Per section: distinct readers reached, total attention-minutes (sum of time in min)
    section_readers = {}  # section → set of reader_ids
    section_attention = {}  # section → sum of seconds

    # Latest week's active readers for reach %
    for ev in engagement:
        s = ev["section"]
        if ev["reader_id"]:
            section_readers.setdefault(s, set()).add(ev["reader_id"])
        if ev["time_on_section"] is not None:
            section_attention[s] = section_attention.get(s, 0) + ev["time_on_section"]

    section_pop_data = []
    for section in CANONICAL_SECTIONS + ["Other (review)"]:
        readers = len(section_readers.get(section, set()))
        attn_min = round(section_attention.get(section, 0) / 60, 1)
        reach_pct = round(readers / latest_ar * 100, 1) if latest_ar else None
        section_pop_data.append({
            "section": section,
            "distinct_readers": readers,
            "reach_pct": reach_pct,
            "attention_minutes": attn_min,
        })

    # Sort by reach for reach ranking, by attention for attention ranking
    by_reach = sorted(section_pop_data, key=lambda d: d["distinct_readers"], reverse=True)
    by_attention = sorted(section_pop_data, key=lambda d: d["attention_minutes"], reverse=True)

    for i, d in enumerate(by_reach):
        d["reach_rank"] = i + 1
    for i, d in enumerate(by_attention):
        d["attention_rank"] = i + 1

    # Merge ranks back
    attention_rank_map = {d["section"]: d["attention_rank"] for d in by_attention}
    for d in section_pop_data:
        d["attention_rank"] = attention_rank_map[d["section"]]

    section_pop_data.sort(key=lambda d: d["distinct_readers"], reverse=True)

    # Caption: note where top-by-reach ≠ top-by-attention
    top_reach = by_reach[0]["section"] if by_reach else None
    top_attention = by_attention[0]["section"] if by_attention else None
    if top_reach != top_attention:
        ranking_caption = (
            f"{top_reach} reaches the most readers, but {top_attention} "
            f"captures the most total attention-minutes — suggesting "
            f"{top_attention} readers spend more time per visit."
        )
    else:
        ranking_caption = (
            f"{top_reach} leads on both reach and total attention — the clear top section."
        )

    # --- Device split for top section by reach ---
    top_section = by_reach[0]["section"] if by_reach else None
    device_counts = Counter()
    for ev in engagement:
        if ev["section"] == top_section and ev["device"]:
            device_counts[ev["device"]] += 1
    total_dev = sum(device_counts.values())
    device_split = [
        {"device": d, "count": c, "share_pct": round(c / total_dev * 100, 1)}
        for d, c in device_counts.most_common()
    ] if total_dev else []
    top_device = device_split[0]["device"] if device_split else None
    top_device_pct = device_split[0]["share_pct"] if device_split else None
    device_takeaway = (
        f"{top_device.capitalize()} accounts for {top_device_pct}% of views "
        f"in {top_section} — optimize placements for {top_device} first."
        if top_device else "Device data unavailable."
    )

    # --- Sponsors ---
    sponsor_agg = {}  # sponsor_name → {spend, impressions, issues}
    for sp in sponsors:
        name = sp["sponsor_name"] or "Unknown"
        entry = sponsor_agg.setdefault(name, {"spend": 0, "impressions": 0, "issues": set()})
        if sp["spend"] is not None:
            entry["spend"] += sp["spend"]
        if sp["impressions"] is not None:
            entry["impressions"] += sp["impressions"]
        if sp["issue_id"]:
            entry["issues"].add(sp["issue_id"])

    sponsor_rows = []
    for name, agg in sponsor_agg.items():
        imp = agg["impressions"]
        spend = round(agg["spend"], 2)
        cpm = round(spend / imp * 1000, 2) if imp > 0 else None
        sponsor_rows.append({
            "sponsor": name,
            "total_spend": spend,
            "total_impressions": imp,
            "issues_run": len(agg["issues"]),
            "cpm": cpm,
        })
    sponsor_rows.sort(key=lambda r: r["total_spend"], reverse=True)

    # --- Orphan rate ---
    sends_ids = {s["issue_id"] for s in sends}
    engagement_issue_ids = [ev["issue_id"] for ev in engagement]
    orphan_count = sum(1 for iid in engagement_issue_ids if iid not in sends_ids)
    orphan_rate = round(orphan_count / len(engagement_issue_ids) * 100, 1) if engagement_issue_ids else 0

    # --- Data quality ---
    total_raw_engagement = 20167  # from profiling
    total_raw_sends = 87
    total_raw_subs = 82
    total_raw_sponsors = 159

    dq = {
        "sends_rows_in": total_raw_sends,
        "sends_rows_out": len(sends),
        "sends_dropped": total_raw_sends - len(sends),
        "subs_rows_in": total_raw_subs,
        "subs_rows_out": len(subscribers),
        "subs_dropped": total_raw_subs - len(subscribers),
        "engagement_rows_in": total_raw_engagement,
        "engagement_rows_out": len(engagement),
        "engagement_dropped": total_raw_engagement - len(engagement),
        "sponsors_rows_in": total_raw_sponsors,
        "sponsors_rows_out": len(sponsors),
        "sponsors_dropped": total_raw_sponsors - len(sponsors),
        "orphan_events": orphan_count,
        "orphan_rate_pct": orphan_rate,
        "bot_sessions_removed": bot_count,
        "other_review_events": other_count,
        "other_review_pct": round(other_count / len(engagement) * 100, 1) if engagement else 0,
    }

    print(f"\n── DATA QUALITY ──")
    print(f"  Sends: {dq['sends_rows_in']} in → {dq['sends_rows_out']} out ({dq['sends_dropped']} dropped)")
    print(f"  Subscribers: {dq['subs_rows_in']} in → {dq['subs_rows_out']} out ({dq['subs_dropped']} dropped)")
    print(f"  Engagement: {dq['engagement_rows_in']} in → {dq['engagement_rows_out']} out ({dq['engagement_dropped']} dropped)")
    print(f"  Sponsors: {dq['sponsors_rows_in']} in → {dq['sponsors_rows_out']} out ({dq['sponsors_dropped']} dropped)")
    print(f"  Orphan engagement events: {orphan_count} ({orphan_rate}%)")
    print(f"  Bot sessions removed from time metrics: {bot_count}")
    print(f"  Events in 'Other (review)': {other_count} ({dq['other_review_pct']}%)")

    # --- Generate summary sentence ---
    summary = (
        f"The Cart grew from {first_ar:,} to {latest_ar:,} active readers "
        f"(+{growth_pct}%) over the reporting period, "
        f"with an average open rate of {avg_open_rate}% and "
        f"${total_sponsor_spend:,.0f} in total sponsor revenue."
        if (first_ar and latest_ar and growth_pct is not None and avg_open_rate)
        else "Performance summary not available — check data quality report."
    )

    return {
        "kpis": kpis,
        "summary_sentence": summary,
        "weekly_readers": weeks_data,
        "section_time": section_time_data,
        "section_popularity": section_pop_data,
        "ranking_caption": ranking_caption,
        "top_section": top_section,
        "device_split": device_split,
        "device_takeaway": device_takeaway,
        "sponsors": sponsor_rows,
        "data_quality": dq,
    }


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("The Cart — Data Cleaning & Report Build")
    print("=" * 50)

    sends = clean_sends()
    subscribers = clean_subscribers()
    engagement, bot_count, other_count = clean_engagement()
    sponsors = clean_sponsors()

    print("\n── COMPUTING METRICS ──")
    report = compute_metrics(sends, subscribers, engagement, sponsors,
                             bot_count, other_count)

    # Serialize (dates → strings)
    def default_serializer(o):
        from datetime import date
        if isinstance(o, date):
            return str(o)
        raise TypeError(f"Object of type {type(o)} not serializable")

    with open(OUT, "w") as f:
        json.dump(report, f, indent=2, default=default_serializer)

    print(f"\n✓ report_data.json written ({OUT.stat().st_size // 1024} KB)")

    # Inject JSON into report.html
    html_path = Path("report.html")
    if html_path.exists():
        html = html_path.read_text()
        json_str = json.dumps(report, default=default_serializer)
        html = html.replace(
            "window.__REPORT_DATA__ = null; // __REPORT_DATA_PLACEHOLDER__",
            f"window.__REPORT_DATA__ = {json_str};"
        )
        html_path.write_text(html)
        print(f"✓ report.html updated with embedded data ({html_path.stat().st_size // 1024} KB)")
    else:
        print("⚠ report.html not found — skipping HTML injection")
    print("\n── ROW COUNT SUMMARY ──")
    dq = report["data_quality"]
    for key in ["sends", "subs", "engagement", "sponsors"]:
        label = {"sends": "Sends", "subs": "Subscribers",
                 "engagement": "Engagement", "sponsors": "Sponsors"}[key]
        print(f"  {label:12s}: {dq[f'{key}_rows_in']:>6,} in  →  {dq[f'{key}_rows_out']:>6,} out  ({dq[f'{key}_dropped']} dropped)")


if __name__ == "__main__":
    main()
