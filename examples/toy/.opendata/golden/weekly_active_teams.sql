---
id: weekly_active_teams
question: "weekly active teams, last 8 weeks"
aliases:
  - "weekly active teams"
  - "how many teams were active each week"
  - "WAT by week"
metric: active_team
owner: "@finance"
status: approved
verified_at: 2026-07-10
expects:
  columns: [week, active_teams]
  min_rows: 1
---
SELECT date_trunc('week', occurred_at) AS week,
       count(DISTINCT team_id)          AS active_teams
FROM   main.events
WHERE  occurred_at >= now() - INTERVAL 56 DAY
GROUP  BY 1
ORDER  BY 1;
