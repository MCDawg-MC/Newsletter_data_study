# The Cart — Data Dictionary (v1)

Internal reference for the four weekly exports from our email platform and on-page
analytics. Schemas below are the *intended* schema. Real exports drift from this.
Treat every field as suspect until validated.

Newsletter: **The Cart**, a weekly ecommerce/deals newsletter.
Cadence: weekly. Issue IDs follow `ISS-1001`, `ISS-1002`, ...

---

## 1. newsletter_sends_raw.csv
One row per issue send. Source: email service provider export.

| column        | intended type | description                                  |
|---------------|---------------|----------------------------------------------|
| issue_id      | string        | Unique issue identifier (`ISS-####`)         |
| send_date     | date          | Date the issue was sent                      |
| subject_line  | string        | Subject line used                            |
| recipients    | integer       | Number of inboxes the issue was delivered to |
| opens         | integer       | Total opens (includes repeat opens)          |
| unique_opens  | integer       | Distinct readers who opened                  |
| clicks        | integer       | Total link clicks                            |

## 2. subscribers_weekly_raw.csv
One row per week. Source: list management export.

| column         | intended type | description                              |
|----------------|---------------|------------------------------------------|
| week           | date          | Week start date                          |
| active_readers | integer       | Active subscribers that week             |
| new_subs       | integer       | New subscribers that week                |
| unsubscribes   | integer       | Unsubscribes that week                   |
| churn_pct      | float         | Unsubscribes as % of prior-week active   |

## 3. section_engagement_raw.csv
One row per reader-section view event. Source: on-page scroll/time tracking beacon.
This is the high-volume table.

| column          | intended type | description                                   |
|-----------------|---------------|-----------------------------------------------|
| event_id        | string        | Unique event id (`EV######`)                  |
| issueID         | string        | Issue the event belongs to (`ISS-####`)       |
| reader_id       | string        | Pseudonymous reader id (`R#####`)             |
| section         | string        | Newsletter section viewed                     |
| time_on_section | integer (sec) | Seconds the reader spent on the section       |
| device          | string        | Device category: mobile, desktop, tablet, app |
| timestamp       | datetime      | When the view occurred                        |

Canonical sections: Deals of the Week, New Arrivals, Editor's Picks,
Tech & Gadgets, Home & Living, Sponsored Spotlight, Reader Q&A.

## 4. sponsors_raw.csv
One row per sponsor placement. Source: ad ops sheet.

| column         | intended type | description                          |
|----------------|---------------|--------------------------------------|
| placement_id   | string        | Unique placement id (`SP####`)       |
| sponsor_name   | string        | Sponsor brand name                   |
| issue          | string        | Issue the placement ran in           |
| section_placed | string        | Section the placement appeared in    |
| spend          | float (USD)   | Amount the sponsor paid              |
| impressions    | integer       | Impressions delivered                |

---

## Join keys
- `newsletter_sends_raw.issue_id` = `section_engagement_raw.issueID` = `sponsors_raw.issue`
- `subscribers_weekly_raw.week` aligns to `newsletter_sends_raw.send_date` by week
