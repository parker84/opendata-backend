-- Toy warehouse for the opendata demo. `opendata init` builds warehouse.duckdb
-- from this on first run. Data is generated relative to "now" so the
-- "last 8 weeks" golden always returns fresh rows.

CREATE TABLE dim_teams (team_id INTEGER, team_name VARCHAR, plan VARCHAR);
INSERT INTO dim_teams VALUES
  (1, 'Acme',     'pro'),
  (2, 'Globex',   'free'),
  (3, 'Initech',  'pro'),
  (4, 'Umbrella', 'enterprise'),
  (5, 'Hooli',    'free');

CREATE TABLE events (event_id BIGINT, team_id INTEGER, occurred_at TIMESTAMP, event_name VARCHAR);
INSERT INTO events
SELECT row_number() OVER ()                       AS event_id,
       tm.team_id                                 AS team_id,
       now() - INTERVAL (gs.d) DAY                AS occurred_at,
       'login'                                    AS event_name
FROM   generate_series(0, 55) AS gs(d)
CROSS JOIN (SELECT unnest([1, 2, 3, 4, 5]) AS team_id) tm
WHERE  (gs.d + tm.team_id) % 2 = 0;               -- varies which teams are active per day
