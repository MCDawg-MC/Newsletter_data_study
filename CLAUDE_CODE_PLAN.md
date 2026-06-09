# Claude Code Plan: The Cart Newsletter Analytics

Build a Python pipeline that ingests four messy raw exports, cleans them, and answers
three sponsor questions. Designed for an agentic Claude Code workflow. Each phase has a
paste-ready prompt and a definition of done.

## The goal (what sponsors pay to see)

1. **Weekly reader count and trend.** How many people read each week, and is it growing.
2. **Time spent per section.** Average and median seconds readers spend on each section.
3. **Most popular sections.** Ranked by reach (share of readers) and by attention (total time).

Every number must be defensible. A wrong number that looks confident is worse than a flagged gap.

---

## Inputs

Four files in `data/raw/`:

- `newsletter_sends_raw.csv` — issue-level email metrics
- `subscribers_weekly_raw.csv` — weekly audience snapshots
- `section_engagement_raw.csv` — per-reader, per-section view events (~20k rows)
- `sponsors_raw.csv` — sponsor placements and spend

See `DATA_DICTIONARY.md` for the intended schema. The real data does not match it.

---

## Known mess to expect (do not assume this list is complete)

Dates: mixed formats in the same column (`2024-01-05`, `01/05/2024`, `Jan 05, 2024`,
`05-Jan-24`, ISO weeks like `2024-W09`, some with time, some blank).

Numbers stored as text: thousands separators (`45,231`), `k` suffix (`45k`), and in
`newsletter_sends.opens` a mix of counts and percentages (`42.1%`) in one column.

Nulls in many disguises: empty, `NA`, `N/A`, `null`, `-`, `#N/A`, `None`.

Categorical chaos: section labels vary by case, whitespace, punctuation, abbreviation,
and typo (`Deals`, `DEALS OF THE WEEK`, `Deals of the Wek`, `Editor's Picks` vs
`Editors Picks` vs a smart-quote variant). Devices have ~5 variants each
(`iPhone`/`Android`/`phone` all mean mobile). Sponsor names have brand variants.

Durations: `150` (seconds), `2m 30s`, `00:02:30`, `2.5 min`, plus negatives, zeros, and
bot sessions of 4000 to 20000 seconds.

Structural: duplicate issue rows (re-sends logged twice), duplicate engagement events
(double-fired beacons), blank rows, an issue id format drift (`ISS1027` vs `ISS-1027`),
and engagement rows for retired sections (`Flash Sale`, `Holiday Gift Guide`, `Newsletter Footer`).

---

## Repo layout

```
the-cart-analytics/
  CLAUDE.md
  data/
    raw/                  # the four *_raw.csv files (read-only, never edit)
    interim/              # per-file cleaned outputs
    processed/            # final analysis-ready tables
  src/
    clean_sends.py
    clean_subscribers.py
    clean_engagement.py
    clean_sponsors.py
    insights.py
    validate.py
  tests/
    test_parsers.py
  reports/
    insights.md           # the sponsor-facing summary
    dashboard.html        # optional Chart.js view
  utils/
    parsers.py            # shared parse_date / parse_number / parse_duration / normalize_label
  run_pipeline.py         # orchestrates clean -> validate -> insights
  README.md
```

Keep `data/raw/` immutable. Every script reads raw or interim and writes a new file. Never overwrite in place.

---

## CLAUDE.md (drop this in the repo root)

```md
# The Cart Analytics — project memory

## What this is
Pipeline that cleans four messy newsletter exports and produces three sponsor metrics:
weekly reader count + trend, time per section, most popular sections.

## Rules
- data/raw is read-only. Never modify it. Write cleaned outputs to data/interim and data/processed.
- All parsing logic lives in utils/parsers.py. Do not inline regex in analysis scripts.
- Every cleaning step must log: rows in, rows out, rows dropped, and why.
- Never silently coerce. If a value will not parse, set it to null and record it in a reject log.
- Prefer median over mean for time-on-section. The distribution has bot outliers.
- Canonical sections are the 7 listed in DATA_DICTIONARY.md. Anything else maps to
  "Other (review)", it does not get dropped or force-fit.
- Show your work. Each insight in reports/insights.md must state how it was computed and
  what was excluded.

## Definition of a good answer
A number is only reported if it survives validation in src/validate.py. Flag gaps, do not fill them with guesses.

## Stack
Python, pandas. Chart.js for the optional dashboard. No heavy ML.
```

---

## Phase 1 — Profile before touching anything

Goal: understand the mess. Do not clean yet.

**Prompt for Claude Code:**
> Read DATA_DICTIONARY.md. Then write `src/profile.py` that loads all four files in
> `data/raw/` as pure strings (dtype=str, keep_default_na=False) and prints, per column:
> row count, null-token frequency, number of unique values, and 10 example raw values.
> For `section_engagement_raw.csv` also list every distinct `section`, every distinct
> `device`, and 20 distinct `time_on_section` formats. Save the profile to
> `reports/profile.txt`. Do not modify any data.

Definition of done: a profile report that enumerates the actual mess. Compare it to the
dictionary and note every mismatch in `reports/profile.txt`.

## Phase 2 — Shared parsers (the foundation)

Goal: one tested place for every messy-value conversion.

**Prompt for Claude Code:**
> Create `utils/parsers.py` with these pure functions, each returning a clean value or
> None on failure (never raise):
> - `parse_number(x)` handles `45,231`, `45k`, plain ints, and null tokens.
> - `parse_percent_or_count(x, base)` for the opens column: if value ends in `%`, return
>   round(base * pct); else parse as a count.
> - `parse_date(x)` tries ISO, US slash, `%b %d, %Y`, `%d-%b-%y`, ISO-week `YYYY-Www`, and
>   datetime variants. Returns a date or None.
> - `parse_duration(x)` returns seconds from `150`, `2m 30s`, `00:02:30`, `2.5 min`.
>   Returns None for null tokens.
> - `normalize_section(x)` maps any variant to one of the 7 canonical sections via a
>   lookup built on lowercased, stripped, punctuation-normalized keys. Unknown -> "Other (review)".
> - `normalize_device(x)` maps to one of: mobile, desktop, tablet, app.
> - `normalize_sponsor(x)` maps brand variants to a canonical name.
> Then write `tests/test_parsers.py` with at least 4 cases per function, including the
> failure cases. Run pytest and fix until green.

Definition of done: pytest passes. Parsers raise nothing and return None on bad input.

## Phase 3 — Clean each file

One script per file. Each reads `data/raw/*`, uses `utils/parsers.py`, writes to
`data/interim/<name>_clean.parquet`, and writes rejected rows to
`data/interim/<name>_rejects.csv` with a reason column.

**Prompt for Claude Code (run once per file, adapt the name):**
> Write `src/clean_sends.py`. Read `data/raw/newsletter_sends_raw.csv` as strings.
> Steps: drop fully blank rows; parse send_date; parse recipients, unique_opens, clicks
> with parse_number; resolve opens with parse_percent_or_count using recipients as base;
> normalize issue_id format (`ISS1027` -> `ISS-1027`); deduplicate on issue_id keeping the
> row with the most non-null fields; flag impossible values (opens > recipients,
> unique_opens > recipients, negative counts) to the reject log rather than dropping
> silently. Log rows in/out/dropped. Write parquet + reject csv.

Repeat for:
- `clean_subscribers.py` — parse week to a week-start date (handle ISO week), parse counts, parse churn_pct to float, dedupe weeks.
- `clean_engagement.py` — normalize section and device, parse timestamp, parse_duration,
  drop events with null or non-positive duration to rejects, cap or flag durations above a
  bot threshold (for example 1800s) rather than averaging them in, normalize issueID, dedupe on event_id.
- `clean_sponsors.py` — normalize sponsor_name, parse spend (money) and impressions, normalize section_placed.

Definition of done: four parquet files in `data/interim/`, four reject logs, and a one-line
summary per file (rows in, out, dropped) printed to console.

## Phase 4 — Validate before computing anything

Goal: catch silent errors. This is the honesty layer.

**Prompt for Claude Code:**
> Write `src/validate.py` that runs assertions on the interim files and writes
> `reports/validation.md`. Checks:
> - every engagement issueID exists in cleaned sends (orphan rate reported, not ignored)
> - no duplicate issue_id in sends, no duplicate event_id in engagement
> - section values are only the 7 canonical plus "Other (review)"; report the count and
>   share of "Other (review)" so we know how much we could not classify
> - time_on_section after cleaning is positive and below the bot threshold
> - weekly active_readers is monotonic-ish (flag week-over-week swings above 25% for review)
> - opens never exceed recipients
> Validation should warn and record, not crash, unless a check is fatal (duplicate keys).

Definition of done: `reports/validation.md` lists every check, pass/fail, and the residual
gaps (orphan rate, unclassified-section share). These gaps get surfaced in the final report, not hidden.

## Phase 5 — Build the processed tables

**Prompt for Claude Code:**
> Write the table builders in `src/insights.py` that read interim parquet and write to
> `data/processed/`:
> - `weekly_readers.parquet`: one row per week with active_readers, new_subs, unsubscribes,
>   churn_pct, unique_opens, and a 4-week rolling average of active_readers.
> - `section_time.parquet`: per section, the median and mean seconds, event count, and a
>   breakdown by device. Use median as the headline metric.
> - `section_popularity.parquet`: per section, distinct readers reached, share of weekly
>   readers (reach), and total attention-minutes (sum of time). Rank by both reach and attention.
> Exclude rejected and "Other (review)" rows from headline metrics but report how many were excluded.

Definition of done: three processed tables, each with a docstring stating its grain and exclusions.

## Phase 6 — Answer the three questions

**Prompt for Claude Code:**
> Write `reports/insights.md` (sponsor-facing). For each of the three questions give the
> answer, the trend, and a one-line method note ("median of cleaned events, bot sessions and
> N unclassified rows excluded"). Include:
> 1. Weekly reader count: latest week, 4-week average, and growth vs the start of the period.
>    Note the holiday spike and summer dip.
> 2. Time per section: a ranked table of median seconds, with the device split for the top section.
> 3. Most popular sections: two rankings, reach and attention, and a note where they disagree.
> End with a "Data quality" section listing orphan rate, unclassified-section share, and
> rows dropped. Keep prose direct and short.

Definition of done: a report a sponsor could read in two minutes, with every number traceable
to a processed table and a method note.

## Phase 7 — Optional dashboard

**Prompt for Claude Code:**
> Build `reports/dashboard.html` as a single self-contained file using Chart.js from a CDN.
> Read the processed tables exported to JSON. Three views: a weekly readers line chart with the
> rolling average, a horizontal bar of median time per section, and a bar of section reach.
> Add a small "data quality" footer with the dropped-row counts.

## Phase 8 — Orchestrate

**Prompt for Claude Code:**
> Write `run_pipeline.py` that runs profile -> clean (all four) -> validate -> insights in
> order, stops on fatal validation failures, and prints a final summary table of row counts at
> each stage. Add a `make run` style entry in README.md.

---

## Sponsor questions mapped to outputs

| Sponsor question            | Source tables                          | Output                                   |
|-----------------------------|----------------------------------------|------------------------------------------|
| Weekly reader count + trend | subscribers_weekly, sends              | weekly_readers.parquet, line chart       |
| Time spent per section      | section_engagement                     | section_time.parquet, bar chart          |
| Most popular sections       | section_engagement (+ sends for reach) | section_popularity.parquet, two rankings |

---

## Failure modes to defend against (portfolio talking points)

These are the mistakes a naive pipeline makes. Calling them out is the point of the project.

- **Mean time-on-section without removing bot sessions.** A few 10000-second events drag the
  mean up. Use median and a bot cap. Show both so the gap is visible.
- **Force-fitting unknown sections.** `Flash Sale` is not one of the seven. Mapping it to the
  nearest canonical section invents data. Route it to "Other (review)" and report the share.
- **Averaging the opens column blindly.** It mixes counts and percentages. Resolve per row first.
- **Counting duplicate beacons as real reads.** Dedup on event_id before any time or reach metric.
- **Joining on a drifting key.** `ISS1027` will not join to `ISS-1027`. Normalize ids first,
  then report orphan rate so a silent join loss cannot hide.
- **Reporting reader counts from a column with `k` suffixes parsed as text.** `48k` sorts and
  sums wrong until parsed to 48000.

The deliverable is not just clean numbers. It is a pipeline that says what it could not clean.
