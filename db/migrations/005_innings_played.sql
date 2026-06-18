-- Migration 005: track defensive innings played per player.
--
-- Adds player_game_stats.innings_played and surfaces a season total in
-- v_player_season_totals so fielding can be rated by errors-per-inning, not
-- just errors-per-game.

alter table player_game_stats add column if not exists innings_played numeric(3, 1);

-- New columns can only be appended to a view via CREATE OR REPLACE, so
-- innings_played is added as the final column.
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
    , 3)                                        as ops,
    coalesce(sum(pgs.innings_played), 0)        as innings_played
from player_game_stats pgs
join players p on p.id = pgs.player_id
join games   g on g.id = pgs.game_id
group by p.id, p.name, p.team_id, g.season;
