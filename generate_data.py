"""
Generates deliberately messy synthetic data for a fictional ecommerce newsletter:
'The Cart' — a major weekly ecommerce/deals newsletter.

Four export sources, each messy in its own way:
  1. newsletter_sends_raw.csv     -> issue-level email metrics (one row per issue, plus dupes)
  2. subscribers_weekly_raw.csv   -> weekly audience snapshots
  3. section_engagement_raw.csv   -> per-reader, per-section scroll/time events (the big one)
  4. sponsors_raw.csv             -> sponsor placements and spend

Messiness is injected on purpose so a cleaning pipeline has something to fix.
Reproducible via fixed seed.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import random
import csv

SEED = 42
np.random.seed(SEED)
random.seed(SEED)

# ----------------------------------------------------------------------
# Underlying "truth" — clean signal we will later corrupt
# ----------------------------------------------------------------------
START = datetime(2024, 1, 1)          # first Monday-ish
N_ISSUES = 78                          # ~18 months of weekly issues
SECTIONS = [
    "Deals of the Week",
    "New Arrivals",
    "Editor's Picks",
    "Tech & Gadgets",
    "Home & Living",
    "Sponsored Spotlight",
    "Reader Q&A",
]
DEVICES = ["mobile", "desktop", "tablet", "app"]

# build issue calendar (weekly)
issue_dates = [START + timedelta(weeks=i) for i in range(N_ISSUES)]

# audience grows from ~210k to ~360k with holiday seasonality
base_readers = np.linspace(210_000, 360_000, N_ISSUES)
seasonal = []
for d in issue_dates:
    bump = 1.0
    if d.month in (11, 12):       # holiday shopping spike
        bump = 1.18
    elif d.month in (1,):         # post-holiday dip
        bump = 0.93
    elif d.month in (7, 8):       # summer lull
        bump = 0.96
    seasonal.append(bump)
true_active = (base_readers * np.array(seasonal) * np.random.normal(1, 0.03, N_ISSUES)).astype(int)

# open rate drifts down slowly (list fatigue), clicks scale with opens
true_open_rate = np.clip(np.linspace(0.42, 0.36, N_ISSUES) + np.random.normal(0, 0.02, N_ISSUES), 0.25, 0.55)
true_unique_opens = (true_active * true_open_rate).astype(int)
true_total_opens = (true_unique_opens * np.random.normal(1.6, 0.1, N_ISSUES)).astype(int)
true_clicks = (true_unique_opens * np.random.uniform(0.18, 0.30, N_ISSUES)).astype(int)

# section popularity weights (Deals dominate, Q&A small). app/mobile read more.
section_weight = {
    "Deals of the Week": 0.30,
    "New Arrivals": 0.16,
    "Editor's Picks": 0.14,
    "Tech & Gadgets": 0.15,
    "Home & Living": 0.12,
    "Sponsored Spotlight": 0.08,
    "Reader Q&A": 0.05,
}
# typical seconds spent reading each section (truth, before corruption)
section_secs = {
    "Deals of the Week": 95,
    "New Arrivals": 55,
    "Editor's Picks": 70,
    "Tech & Gadgets": 80,
    "Home & Living": 60,
    "Sponsored Spotlight": 30,
    "Reader Q&A": 45,
}

# ----------------------------------------------------------------------
# Messiness helpers
# ----------------------------------------------------------------------
NULL_TOKENS = ["", "NA", "N/A", "null", "NULL", "-", "#N/A", "None"]

def messy_date(d):
    """Return a date in one of several inconsistent string formats; sometimes blank."""
    r = random.random()
    if r < 0.04:
        return random.choice(NULL_TOKENS)
    fmt = random.random()
    if fmt < 0.45:
        return d.strftime("%Y-%m-%d")               # 2024-01-01
    elif fmt < 0.70:
        return d.strftime("%m/%d/%Y")               # 01/01/2024
    elif fmt < 0.85:
        return d.strftime("%b %d, %Y")              # Jan 01, 2024
    elif fmt < 0.95:
        return d.strftime("%d-%b-%y")               # 01-Jan-24
    else:
        return d.strftime("%Y-%m-%d %H:%M:%S")      # with time

def messy_int(n):
    """Return an int as a string, sometimes with thousands separators or k-suffix; sometimes null."""
    r = random.random()
    if r < 0.03:
        return random.choice(NULL_TOKENS)
    style = random.random()
    if style < 0.55:
        return str(n)
    elif style < 0.85:
        return f"{n:,}"                              # 45,231
    else:
        return f"{round(n/1000)}k"                   # 45k

def messy_section(name):
    """Corrupt a section label: casing, whitespace, abbreviations, typos."""
    variants = {
        "Deals of the Week": ["Deals of the Week", "deals of the week", "DEALS OF THE WEEK",
                              "Deals ", " Deals of the Week", "Deals of the Wek", "deals"],
        "New Arrivals": ["New Arrivals", "new arrivals", "New  Arrivals", "NewArrivals", "new_arrivals"],
        "Editor's Picks": ["Editor's Picks", "Editors Picks", "editor's picks", "Editor\u2019s Picks", "EDITORS PICKS"],
        "Tech & Gadgets": ["Tech & Gadgets", "Tech and Gadgets", "tech & gadgets", "Tech&Gadgets", "Tech / Gadgets"],
        "Home & Living": ["Home & Living", "Home and Living", "home & living", "Home&Living", "Home  & Living"],
        "Sponsored Spotlight": ["Sponsored Spotlight", "sponsored spotlight", "Sponsored", "Sponsor Spotlight", "SPONSORED SPOTLIGHT"],
        "Reader Q&A": ["Reader Q&A", "reader q&a", "Reader QandA", "Q&A", "Reader Q & A"],
    }
    return random.choice(variants[name])

def messy_device(dev):
    variants = {
        "mobile": ["mobile", "Mobile", "MOBILE", "phone", "iPhone", "Android"],
        "desktop": ["desktop", "Desktop", "web", "Web", "PC"],
        "tablet": ["tablet", "Tablet", "iPad", "TABLET"],
        "app": ["app", "App", "mobile app", "iOS App", "Android App"],
    }
    return random.choice(variants[dev])

def messy_duration(secs):
    """Express a duration in inconsistent formats; inject bot/garbage values."""
    r = random.random()
    if r < 0.04:
        return random.choice(NULL_TOKENS)
    if r < 0.06:
        return str(random.choice([-5, -30, 0]))      # invalid / negative
    if r < 0.08:
        return str(random.randint(4000, 20000))      # bot session, absurd seconds
    style = random.random()
    if style < 0.45:
        return str(secs)                             # raw seconds
    elif style < 0.65:
        m, s = divmod(secs, 60)
        return f"{m}m {s}s"                          # 1m 35s
    elif style < 0.82:
        m, s = divmod(secs, 60)
        return f"00:{m:02d}:{s:02d}"                 # 00:01:35
    else:
        return f"{round(secs/60, 1)} min"            # 1.6 min

def messy_money(amount):
    r = random.random()
    if r < 0.03:
        return random.choice(NULL_TOKENS)
    style = random.random()
    if style < 0.4:
        return f"${amount:,.0f}"                      # $5,000
    elif style < 0.65:
        return f"{amount:,.0f} USD"                   # 5,000 USD
    elif style < 0.85:
        return f"{round(amount/1000)}k"              # 5k
    else:
        return str(int(amount))                      # 5000

# ----------------------------------------------------------------------
# 1) newsletter_sends_raw.csv
# ----------------------------------------------------------------------
sends_rows = []
for i in range(N_ISSUES):
    issue_id = f"ISS-{1001+i}"
    subject = random.choice([
        "Your weekly deals are here", "Don't miss these drops", "Top picks this week",
        "New arrivals + flash sale", "The best of the week \u2014 inside", "Weekend deals roundup",
    ])
    recipients = true_active[i]
    # occasionally store opens as a percentage instead of a count (source-system bug)
    if random.random() < 0.12:
        opens_field = f"{round(true_open_rate[i]*100,1)}%"
    else:
        opens_field = messy_int(int(true_total_opens[i]))
    row = {
        "issue_id": issue_id,
        "send_date": messy_date(issue_dates[i]),
        "subject_line": subject,
        "recipients": messy_int(int(recipients)),
        "opens": opens_field,
        "unique_opens": messy_int(int(true_unique_opens[i])),
        "clicks": messy_int(int(true_clicks[i])),
    }
    sends_rows.append(row)

# inject ~6 duplicate issue rows (re-sends logged twice), slightly varied
for _ in range(6):
    dup = dict(random.choice(sends_rows))
    sends_rows.append(dup)

# inject a few fully blank-ish rows
for _ in range(3):
    sends_rows.append({k: "" for k in sends_rows[0].keys()})

random.shuffle(sends_rows)
df_sends = pd.DataFrame(sends_rows)

# ----------------------------------------------------------------------
# 2) subscribers_weekly_raw.csv
# ----------------------------------------------------------------------
sub_rows = []
prev_active = true_active[0]
for i in range(N_ISSUES):
    d = issue_dates[i]
    active = true_active[i]
    new_subs = int(active * np.random.uniform(0.02, 0.04))
    unsubs = int(active * np.random.uniform(0.008, 0.018))
    churn = round(unsubs / max(prev_active, 1) * 100, 2)
    # week label: mix ISO week and date string
    if random.random() < 0.5:
        week_label = d.strftime("%Y-%m-%d")
    else:
        iso = d.isocalendar()
        week_label = f"{iso[0]}-W{iso[1]:02d}"
    sub_rows.append({
        "week": week_label,
        "active_readers": messy_int(active),
        "new_subs": messy_int(new_subs),
        "unsubscribes": messy_int(unsubs),
        "churn_pct": random.choice([f"{churn}%", str(churn), f"{churn} %"]),
    })
    prev_active = active

# duplicate a couple of weeks
for _ in range(4):
    sub_rows.append(dict(random.choice(sub_rows)))
random.shuffle(sub_rows)
df_subs = pd.DataFrame(sub_rows)

# ----------------------------------------------------------------------
# 3) section_engagement_raw.csv  (the large, messy one)
# ----------------------------------------------------------------------
eng_rows = []
event_counter = 1
section_names = list(section_weight.keys())
section_probs = np.array([section_weight[s] for s in section_names])
section_probs = section_probs / section_probs.sum()

for i in range(N_ISSUES):
    issue_id = f"ISS-{1001+i}"
    # sample size scales loosely with audience but kept manageable
    n_events = int(np.random.uniform(180, 320))
    for _ in range(n_events):
        sec_true = np.random.choice(section_names, p=section_probs)
        dev_true = random.choice(DEVICES)
        base = section_secs[sec_true]
        # mobile/app read a bit shorter, desktop longer
        mult = {"mobile": 0.85, "app": 0.9, "tablet": 1.0, "desktop": 1.2}[dev_true]
        secs = max(3, int(np.random.gamma(2.0, base * mult / 2.0)))
        ts = issue_dates[i] + timedelta(hours=random.randint(0, 72),
                                        minutes=random.randint(0, 59))
        eng_rows.append({
            "event_id": f"EV{event_counter:06d}",
            "issueID": issue_id if random.random() > 0.05 else issue_id.replace("ISS-", "ISS"),  # id format drift
            "reader_id": f"R{random.randint(1, 90000):05d}",
            "section": messy_section(sec_true),
            "time_on_section": messy_duration(secs),
            "device": messy_device(dev_true),
            "timestamp": messy_date(ts) if random.random() > 0.5 else ts.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        event_counter += 1

# inject duplicate events (double-fired analytics beacons)
n_dupes = int(len(eng_rows) * 0.02)
for _ in range(n_dupes):
    eng_rows.append(dict(random.choice(eng_rows)))

# inject some rows with a totally unknown section (tracking on a retired section)
for _ in range(40):
    eng_rows.append({
        "event_id": f"EV{event_counter:06d}",
        "issueID": f"ISS-{1001+random.randint(0,N_ISSUES-1)}",
        "reader_id": f"R{random.randint(1,90000):05d}",
        "section": random.choice(["Flash Sale", "Holiday Gift Guide", "", "Newsletter Footer"]),
        "time_on_section": messy_duration(random.randint(5, 120)),
        "device": messy_device(random.choice(DEVICES)),
        "timestamp": messy_date(issue_dates[random.randint(0, N_ISSUES-1)]),
    })
    event_counter += 1

random.shuffle(eng_rows)
df_eng = pd.DataFrame(eng_rows)

# ----------------------------------------------------------------------
# 4) sponsors_raw.csv
# ----------------------------------------------------------------------
SPONSORS = {
    "Acme Supplies": ["Acme Supplies", "Acme Supplies Inc", "acme supplies", "ACME"],
    "NorthPeak Outdoors": ["NorthPeak Outdoors", "North Peak Outdoors", "NorthPeak", "northpeak outdoors"],
    "BrightHome": ["BrightHome", "Bright Home", "BRIGHTHOME", "Bright-Home"],
    "Volt Electronics": ["Volt Electronics", "VOLT Electronics", "Volt Elec.", "volt electronics"],
    "Pure Wellness Co": ["Pure Wellness Co", "Pure Wellness", "PureWellness Co.", "pure wellness co"],
}
sponsor_rows = []
sp_counter = 1
for i in range(N_ISSUES):
    issue_id = f"ISS-{1001+i}"
    # not every issue has every sponsor; 1-3 placements per issue
    for sponsor in random.sample(list(SPONSORS.keys()), k=random.randint(1, 3)):
        spend = np.random.choice([2500, 5000, 7500, 10000, 12000])
        impressions = int(true_unique_opens[i] * np.random.uniform(0.4, 0.9))
        sponsor_rows.append({
            "placement_id": f"SP{sp_counter:04d}",
            "sponsor_name": random.choice(SPONSORS[sponsor]),
            "issue": issue_id,
            "section_placed": messy_section(random.choice(SECTIONS)),
            "spend": messy_money(spend),
            "impressions": messy_int(impressions),
        })
        sp_counter += 1

random.shuffle(sponsor_rows)
df_sponsors = pd.DataFrame(sponsor_rows)

# ----------------------------------------------------------------------
# Write files (with some encoding gremlins already embedded via smart quotes)
# ----------------------------------------------------------------------
df_sends.to_csv("newsletter_sends_raw.csv", index=False, quoting=csv.QUOTE_MINIMAL)
df_subs.to_csv("subscribers_weekly_raw.csv", index=False, quoting=csv.QUOTE_MINIMAL)
df_eng.to_csv("section_engagement_raw.csv", index=False, quoting=csv.QUOTE_MINIMAL)
df_sponsors.to_csv("sponsors_raw.csv", index=False, quoting=csv.QUOTE_MINIMAL)

print("Rows written:")
print("  sends      :", len(df_sends))
print("  subscribers:", len(df_subs))
print("  engagement :", len(df_eng))
print("  sponsors   :", len(df_sponsors))
print()
print("Sample sends:")
print(df_sends.head(6).to_string())
print()
print("Sample engagement:")
print(df_eng.head(8).to_string())
