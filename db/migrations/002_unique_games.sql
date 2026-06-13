-- Migration 002: prevent duplicate games (one game per date + matchup).
--
-- IMPORTANT: a unique index can't be created while duplicates still exist.
-- This migration first removes duplicate games, keeping the copy that has the
-- MOST player stat lines (i.e. the real import, not an empty failed attempt),
-- with the earliest one as a tie-breaker. Deleting a game cascades to its
-- innings, player_game_stats, and team_game_stats.
--
-- NOTE: if you also have duplicate TEAMS (same name created more than once),
-- consolidate those first (so a game's home/away ids line up), otherwise the
-- "same matchup" grouping below won't see them as duplicates. Find them with:
--   select name, count(*) from teams group by name having count(*) > 1;

delete from games
where id in (
    select id from (
        select
            g.id,
            row_number() over (
                partition by g.game_date, g.home_team_id, g.away_team_id
                order by (select count(*) from player_game_stats s where s.game_id = g.id) desc,
                         g.created_at asc
            ) as rn
        from games g
    ) ranked
    where ranked.rn > 1
);

create unique index if not exists uq_games_date_teams
    on games (game_date, home_team_id, away_team_id);
