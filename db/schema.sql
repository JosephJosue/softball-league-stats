-- =====================================================================
-- Softball League Stats — Supabase / PostgreSQL schema
-- =====================================================================
-- Run this whole file in the Supabase SQL Editor (one shot).
-- It is safe to re-run: tables use "if not exists", policies are dropped
-- before re-creation, and views use "create or replace".
--
-- Security model (two roles, enforced by Row Level Security):
--   * anon          -> Viewers. Read-only (no login required).
--   * authenticated -> Admins. Full read/write (must log in via Auth).
-- =====================================================================

-- gen_random_uuid() lives in pgcrypto.
create extension if not exists pgcrypto;


-- ---------------------------------------------------------------------
-- Reference table: positions (seeded below)
-- ---------------------------------------------------------------------
create table if not exists positions (
    id        uuid primary key default gen_random_uuid(),
    code      text unique not null,                  -- 'SS', '1B', 'P', ...
    name      text not null,                         -- 'Shortstop'
    category  text not null                          -- battery | infield | outfield | util
);


-- ---------------------------------------------------------------------
-- teams
-- ---------------------------------------------------------------------
create table if not exists teams (
    id            uuid primary key default gen_random_uuid(),
    name          text not null,
    abbreviation  text,
    season        text,                              -- e.g. '2026-Spring'
    created_at    timestamptz default now()
);


-- ---------------------------------------------------------------------
-- players
-- ---------------------------------------------------------------------
create table if not exists players (
    id                   uuid primary key default gen_random_uuid(),
    name                 text not null,
    team_id              uuid references teams(id) on delete set null,
    jersey_number        int,
    primary_position_id  uuid references positions(id),
    bats                 text check (bats in ('L', 'R', 'S')),
    throws               text check (throws in ('L', 'R')),
    active               boolean default true,
    created_at           timestamptz default now()
);


-- ---------------------------------------------------------------------
-- games
-- ---------------------------------------------------------------------
create table if not exists games (
    id            uuid primary key default gen_random_uuid(),
    game_date     date not null,
    season        text,
    home_team_id  uuid references teams(id),
    away_team_id  uuid references teams(id),
    home_score    int default 0,
    away_score    int default 0,
    location      text,
    status        text default 'final'
                      check (status in ('scheduled', 'in_progress', 'final')),
    notes         text,
    created_at    timestamptz default now()
);


-- ---------------------------------------------------------------------
-- innings  (inning-by-inning line score, one row per team-half)
-- ---------------------------------------------------------------------
create table if not exists innings (
    id             uuid primary key default gen_random_uuid(),
    game_id        uuid references games(id) on delete cascade,
    inning_number  int not null,
    team_id        uuid references teams(id),
    half           text check (half in ('top', 'bottom')),
    runs           int default 0,
    hits           int default 0,
    errors         int default 0,
    unique (game_id, inning_number, half)
);


-- ---------------------------------------------------------------------
-- player_game_stats  (one row per player per game = a box-score line)
-- ---------------------------------------------------------------------
-- "tb" (total bases) is GENERATED so it can never drift from H/2B/3B/HR.
-- Pitching columns are nullable — only populated for players who pitched.
create table if not exists player_game_stats (
    id           uuid primary key default gen_random_uuid(),
    game_id      uuid references games(id) on delete cascade,
    player_id    uuid references players(id) on delete cascade,
    team_id      uuid references teams(id),
    position_id  uuid references positions(id),     -- position played this game

    -- Batting (raw counting stats)
    ab       int default 0,
    r        int default 0,
    h        int default 0,
    rbi      int default 0,
    bb       int default 0,
    so       int default 0,
    doubles  int default 0,                          -- 2B
    triples  int default 0,                          -- 3B
    hr       int default 0,
    lob      int default 0,

    -- Total bases: singles*1 + 2B*2 + 3B*3 + HR*4  ==  h + 2B + 2*3B + 3*HR
    tb int generated always as (h + doubles + 2 * triples + 3 * hr) stored,

    -- Defense
    errors int default 0,

    -- Pitching (nullable; only for pitchers)
    ip    numeric(4, 1),                             -- innings pitched, e.g. 5.2
    p_h   int,
    p_r   int,
    er    int,
    p_bb  int,
    p_so  int,
    p_hr  int,

    created_at timestamptz default now(),
    unique (game_id, player_id)
);


-- ---------------------------------------------------------------------
-- team_game_stats  (one row per team per game; entered from box totals)
-- ---------------------------------------------------------------------
-- Stored (not purely derived) so a scorecard's team line can be entered
-- directly, then reconciled against the sum of player rows.
create table if not exists team_game_stats (
    id        uuid primary key default gen_random_uuid(),
    game_id   uuid references games(id) on delete cascade,
    team_id   uuid references teams(id),
    runs    int default 0,
    hits    int default 0,
    errors  int default 0,
    lob     int default 0,
    ab      int default 0,
    bb      int default 0,
    so      int default 0,
    created_at timestamptz default now(),
    unique (game_id, team_id)
);


-- ---------------------------------------------------------------------
-- Indexes (foreign keys + common filter columns)
-- ---------------------------------------------------------------------
create index if not exists idx_players_team   on players(team_id);
create index if not exists idx_games_date      on games(game_date);
create index if not exists idx_games_season     on games(season);
create index if not exists idx_games_home       on games(home_team_id);
create index if not exists idx_games_away       on games(away_team_id);
create index if not exists idx_innings_game     on innings(game_id);
create index if not exists idx_pgs_player       on player_game_stats(player_id);
create index if not exists idx_pgs_game         on player_game_stats(game_id);
create index if not exists idx_pgs_team         on player_game_stats(team_id);
create index if not exists idx_pgs_position     on player_game_stats(position_id);
create index if not exists idx_tgs_game         on team_game_stats(game_id);
create index if not exists idx_tgs_team         on team_game_stats(team_id);


-- =====================================================================
-- Row Level Security
-- =====================================================================
-- Pattern for every table:
--   * SELECT  -> anon + authenticated (public read)
--   * ALL (write) -> authenticated only (admins logged in via Auth)
-- The anon key therefore CANNOT write, even if the UI is bypassed.

do $$
declare
    t text;
    tables text[] := array[
        'positions', 'teams', 'players', 'games',
        'innings', 'player_game_stats', 'team_game_stats'
    ];
begin
    foreach t in array tables loop
        execute format('alter table %I enable row level security;', t);

        -- Drop existing policies first so this script is re-runnable.
        execute format('drop policy if exists %I on %I;', t || '_read_all', t);
        execute format('drop policy if exists %I on %I;', t || '_write_auth', t);

        -- Public read.
        execute format(
            'create policy %I on %I for select to anon, authenticated using (true);',
            t || '_read_all', t
        );

        -- Authenticated (admin) write: insert / update / delete.
        execute format(
            'create policy %I on %I for all to authenticated using (true) with check (true);',
            t || '_write_auth', t
        );
    end loop;
end $$;


-- =====================================================================
-- Analytics views (computed stats: AVG / OBP / SLG / OPS)
-- =====================================================================
-- security_invoker = on  -> the view runs with the caller's RLS, so anon
-- read access flows through correctly.

-- Per-player, per-season offensive totals + rate stats.
create or replace view v_player_season_totals
with (security_invoker = on) as
select
    p.id                                       as player_id,
    p.name                                     as player_name,
    p.team_id,
    g.season,
    count(distinct pgs.game_id)                as games,
    sum(pgs.ab)                                as ab,
    sum(pgs.r)                                 as r,
    sum(pgs.h)                                 as h,
    sum(pgs.rbi)                               as rbi,
    sum(pgs.bb)                                as bb,
    sum(pgs.so)                                as so,
    sum(pgs.doubles)                           as doubles,
    sum(pgs.triples)                           as triples,
    sum(pgs.hr)                                as hr,
    sum(pgs.tb)                                as tb,
    sum(pgs.errors)                            as errors,
    round(sum(pgs.h)::numeric
          / nullif(sum(pgs.ab), 0), 3)         as avg,
    round((sum(pgs.h) + sum(pgs.bb))::numeric
          / nullif(sum(pgs.ab) + sum(pgs.bb), 0), 3) as obp,
    round(sum(pgs.tb)::numeric
          / nullif(sum(pgs.ab), 0), 3)         as slg,
    round(
        (sum(pgs.h) + sum(pgs.bb))::numeric
            / nullif(sum(pgs.ab) + sum(pgs.bb), 0)
        + sum(pgs.tb)::numeric
            / nullif(sum(pgs.ab), 0)
    , 3)                                        as ops
from player_game_stats pgs
join players p on p.id = pgs.player_id
join games   g on g.id = pgs.game_id
group by p.id, p.name, p.team_id, g.season;


-- Per-team, per-season totals.
create or replace view v_team_season_totals
with (security_invoker = on) as
select
    t.id                            as team_id,
    t.name                          as team_name,
    g.season,
    count(distinct tgs.game_id)     as games,
    sum(tgs.runs)                   as runs,
    sum(tgs.hits)                   as hits,
    sum(tgs.errors)                 as errors,
    sum(tgs.lob)                    as lob,
    sum(tgs.ab)                     as ab,
    sum(tgs.bb)                     as bb,
    sum(tgs.so)                     as so,
    round(sum(tgs.hits)::numeric
          / nullif(sum(tgs.ab), 0), 3) as team_avg
from team_game_stats tgs
join teams t on t.id = tgs.team_id
join games g on g.id = tgs.game_id
group by t.id, t.name, g.season;


-- Position leaderboards: player offensive output grouped by position played.
create or replace view v_position_leaders
with (security_invoker = on) as
select
    pos.code                        as position_code,
    pos.name                        as position_name,
    pos.category,
    p.id                            as player_id,
    p.name                          as player_name,
    g.season,
    sum(pgs.ab)                     as ab,
    sum(pgs.h)                      as h,
    sum(pgs.hr)                     as hr,
    sum(pgs.rbi)                    as rbi,
    sum(pgs.errors)                 as errors,
    round(sum(pgs.h)::numeric
          / nullif(sum(pgs.ab), 0), 3) as avg
from player_game_stats pgs
join positions pos on pos.id = pgs.position_id
join players   p   on p.id   = pgs.player_id
join games     g   on g.id   = pgs.game_id
group by pos.code, pos.name, pos.category, p.id, p.name, g.season;


-- =====================================================================
-- Seed: positions
-- =====================================================================
insert into positions (code, name, category) values
    ('P',  'Pitcher',             'battery'),
    ('C',  'Catcher',             'battery'),
    ('1B', 'First Base',          'infield'),
    ('2B', 'Second Base',         'infield'),
    ('3B', 'Third Base',          'infield'),
    ('SS', 'Shortstop',           'infield'),
    ('LF', 'Left Field',          'outfield'),
    ('CF', 'Center Field',        'outfield'),
    ('RF', 'Right Field',         'outfield'),
    ('SF', 'Short Fielder/Rover', 'outfield'),
    ('DH', 'Designated Hitter',   'util'),
    ('EH', 'Extra Hitter',        'util')
on conflict (code) do nothing;

-- =====================================================================
-- Done. Verify with:
--   select tablename from pg_tables where schemaname = 'public';
--   select * from pg_policies where schemaname = 'public';
-- =====================================================================
