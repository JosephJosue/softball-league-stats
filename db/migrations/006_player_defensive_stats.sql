-- Migration 006: detailed defensive stats (manually compiled from replays).
--
-- PO (putouts), A (assists), E (errors), DP (double plays), OPO (chances),
-- plus throw accuracy (good vs total throws). Enables real Fielding % instead
-- of an errors-only metric. Aggregate per player (season defaults to 'all').

create table if not exists player_defensive_stats (
    id            uuid primary key default gen_random_uuid(),
    player_id     uuid references players(id) on delete cascade,
    season        text not null default 'all',
    games         int default 0,
    po            int default 0,
    a             int default 0,
    e             int default 0,
    dp            int default 0,
    opo           int default 0,
    good_throws   int default 0,
    total_throws  int default 0,
    created_at    timestamptz default now(),
    unique (player_id, season)
);

create index if not exists idx_pds_player on player_defensive_stats(player_id);

alter table player_defensive_stats enable row level security;
drop policy if exists player_defensive_stats_read_all on player_defensive_stats;
drop policy if exists player_defensive_stats_write_auth on player_defensive_stats;
create policy player_defensive_stats_read_all on player_defensive_stats
    for select to anon, authenticated using (true);
create policy player_defensive_stats_write_auth on player_defensive_stats
    for all to authenticated using (true) with check (true);
