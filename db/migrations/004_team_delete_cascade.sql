-- Migration 004: deleting a team cascades to its games and all related stats.
--
-- Migration 003 cascaded players, but teams are also referenced by games
-- (home/away), innings, player_game_stats, and team_game_stats. Without
-- cascade, deleting a team that has played raises a foreign-key error. This
-- switches every team reference to ON DELETE CASCADE, so removing a team
-- removes its games (and their innings/stats) and its players (and theirs).

alter table games drop constraint if exists games_home_team_id_fkey;
alter table games add constraint games_home_team_id_fkey
    foreign key (home_team_id) references teams(id) on delete cascade;

alter table games drop constraint if exists games_away_team_id_fkey;
alter table games add constraint games_away_team_id_fkey
    foreign key (away_team_id) references teams(id) on delete cascade;

alter table innings drop constraint if exists innings_team_id_fkey;
alter table innings add constraint innings_team_id_fkey
    foreign key (team_id) references teams(id) on delete cascade;

alter table player_game_stats drop constraint if exists player_game_stats_team_id_fkey;
alter table player_game_stats add constraint player_game_stats_team_id_fkey
    foreign key (team_id) references teams(id) on delete cascade;

alter table team_game_stats drop constraint if exists team_game_stats_team_id_fkey;
alter table team_game_stats add constraint team_game_stats_team_id_fkey
    foreign key (team_id) references teams(id) on delete cascade;
