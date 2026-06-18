-- Migration 003: every player must belong to exactly one team.
--
-- Changes:
--   * team_id becomes NOT NULL (a player can't be team-less)
--   * the foreign key becomes ON DELETE CASCADE (deleting a team deletes its
--     players, whose game stats already cascade from players)
--
-- Any existing team-less players are removed first (they violate NOT NULL and,
-- under the new rule, shouldn't exist).

delete from players where team_id is null;

alter table players drop constraint if exists players_team_id_fkey;

alter table players alter column team_id set not null;

alter table players
    add constraint players_team_id_fkey
    foreign key (team_id) references teams(id) on delete cascade;
