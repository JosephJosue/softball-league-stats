"""Parser for GameChanger-style softball scorecard PDFs.

These PDFs put the two teams SIDE BY SIDE (away on the left, home on the right)
and split the data across regions:
  * header line .... "Away  A - H  Home"  + date
  * line score ..... runs per inning + R/H/E per team
  * BATTING ........ name (POS) AB R H RBI BB SO  -- per side, ending in "Totals"
  * annotations .... "2B:", "3B:", "HR:" give extra-base hits per player;
                     "LOB:" gives the team total (errors come from "E:")
  * PITCHING ....... name IP H R ER BB SO HR -- per side, ending in "Totals"
  * "E:" line ...... errors per player

We use word coordinates to split each physical line into a left/right column
(x ~= 307 on a 612-pt page), parse stat rows by their trailing numbers, and
recover extra-base hits + errors from the annotation text by fuzzy name match
(table names are truncated with "…"; annotation names are full).
"""

from __future__ import annotations

import datetime
import io
import re
from dataclasses import dataclass, field

import pdfplumber

X_SPLIT = 307  # left column < X_SPLIT <= right column (page width 612)
_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)


@dataclass
class PlayerStat:
    name: str
    position: str | None = None
    ab: int = 0
    r: int = 0
    h: int = 0
    rbi: int = 0
    bb: int = 0
    so: int = 0
    doubles: int = 0
    triples: int = 0
    hr: int = 0
    errors: int = 0
    ip: float | None = None
    p_h: int | None = None
    p_r: int | None = None
    er: int | None = None
    p_bb: int | None = None
    p_so: int | None = None
    p_hr: int | None = None


@dataclass
class GameCard:
    date: datetime.date | None = None
    away_team: str = ""
    home_team: str = ""
    away_score: int = 0
    home_score: int = 0
    away_players: list[PlayerStat] = field(default_factory=list)
    home_players: list[PlayerStat] = field(default_factory=list)
    away_innings: list[int] = field(default_factory=list)
    home_innings: list[int] = field(default_factory=list)
    away_totals: dict = field(default_factory=dict)
    home_totals: dict = field(default_factory=dict)
    away_team_e: int | None = None
    home_team_e: int | None = None
    away_lob: int | None = None
    home_lob: int | None = None


# --- small helpers --------------------------------------------------------

def _is_int(tok: str) -> bool:
    return bool(re.fullmatch(r"-?\d+", tok))


def _is_num(tok: str) -> bool:
    return bool(re.fullmatch(r"-?\d+(\.\d+)?", tok))


def _key(name: str) -> str:
    """Normalized name key for fuzzy matching (alnum, lowercase, no '…')."""
    return re.sub(r"[^a-z0-9]", "", name.lower().replace("…", ""))


def _physical_lines(page, tol: float = 3.0) -> list[list[dict]]:
    """Group a page's words into visual lines, each sorted left-to-right.

    Words on the same row can have tops that differ by a pixel or two (e.g. a
    team abbreviation vs. its numbers), so we cluster within `tol` rather than
    grouping by exact top.
    """
    words = sorted(page.extract_words(), key=lambda w: (w["top"], w["x0"]))
    lines: list[list[dict]] = []
    current: list[dict] = []
    anchor: float | None = None
    for w in words:
        if anchor is None or abs(w["top"] - anchor) <= tol:
            current.append(w)
            anchor = w["top"] if anchor is None else anchor
        else:
            lines.append(sorted(current, key=lambda x: x["x0"]))
            current = [w]
            anchor = w["top"]
    if current:
        lines.append(sorted(current, key=lambda x: x["x0"]))
    return lines


def _split_sides(line: list[dict]) -> tuple[list[str], list[str]]:
    """Split one physical line's words into (left_tokens, right_tokens)."""
    left = [w["text"] for w in line if w["x0"] < X_SPLIT]
    right = [w["text"] for w in line if w["x0"] >= X_SPLIT]
    return left, right


def _parse_stat_row(tokens: list[str], n: int) -> tuple[str, str | None, list[str]] | None:
    """Parse 'Name (POS) n1 n2 ...' into (name, position, [n numbers])."""
    if len(tokens) < n + 1:
        return None
    nums = tokens[-n:]
    if not all(_is_num(t) for t in nums):
        return None
    name_tokens = tokens[:-n]
    position = None
    if name_tokens and name_tokens[-1].startswith("(") and name_tokens[-1].endswith(")"):
        position = name_tokens[-1].strip("()")
        name_tokens = name_tokens[:-1]
    name = " ".join(name_tokens).replace("…", "").strip()
    if not name:
        return None
    return name, position, nums


def _match(name: str, players: list[PlayerStat]) -> PlayerStat | None:
    """Fuzzy-match an annotation name to a parsed player (prefix-based)."""
    k = _key(name)
    best: PlayerStat | None = None
    for p in players:
        pk = _key(p.name)
        if pk and (k.startswith(pk) or pk.startswith(k)):
            if best is None or len(_key(best.name)) < len(pk):
                best = p
    return best


def _split_labeled(blob: str) -> dict[str, str]:
    """Split 'A: ... B: ...' annotation text into {label: segment}."""
    out: dict[str, str] = {}
    matches = list(re.finditer(r"([0-9A-Za-z\-]{1,4}):", blob))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(blob)
        out.setdefault(m.group(1), "")
        out[m.group(1)] += " " + blob[start:end]
    return out


def _name_counts(segment: str) -> list[tuple[str, int]]:
    """Parse 'Name, Name 2, Name' -> [(name, count)] (trailing int = count)."""
    items: list[tuple[str, int]] = []
    for chunk in segment.split(","):
        toks = chunk.strip().rstrip(".").split()
        if not toks:
            continue
        count = 1
        if toks[-1].isdigit():
            count = int(toks[-1])
            toks = toks[:-1]
        name = " ".join(toks).strip()
        if name:
            items.append((name, count))
    return items


def _first_int(segment: str) -> int | None:
    m = re.search(r"\d+", segment)
    return int(m.group()) if m else None


# --- main parse -----------------------------------------------------------

def parse(data: bytes) -> GameCard | None:
    """Parse a GameChanger scorecard PDF into a GameCard, or None if it
    doesn't look like one."""
    card = GameCard()
    bat_anno = {"L": "", "R": ""}
    pit_anno = {"L": "", "R": ""}
    mode = "header"          # header -> linescore -> batting -> pitching
    skip_next = False
    away_done = home_done = False  # batting Totals reached per side

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            for line in _physical_lines(page):
                text = " ".join(w["text"] for w in line).strip()
                if not text or text.startswith("Scorekeeping"):
                    continue
                if skip_next:
                    skip_next = False
                    continue

                # --- header (team names + score) ---
                if mode == "header":
                    m = re.match(r"^(.*?)\s+(\d+)\s*-\s*(\d+)\s+(.*)$", text)
                    if m:
                        card.away_team = m.group(1).strip()
                        card.away_score = int(m.group(2))
                        card.home_score = int(m.group(3))
                        card.home_team = m.group(4).strip()
                        mode = "linescore"
                    continue

                # --- date (anywhere) ---
                if card.date is None:
                    dm = re.search(rf"({_MONTHS})\s+(\d{{1,2}}),\s+(\d{{4}})", text)
                    if dm:
                        try:
                            card.date = datetime.datetime.strptime(
                                dm.group(0), "%B %d, %Y"
                            ).date()
                        except ValueError:
                            pass

                # --- section markers ---
                if text == "BATTING":
                    mode = "batting"
                    skip_next = True  # the column header row
                    continue
                if text == "PITCHING":
                    mode = "pitching"
                    skip_next = True
                    continue

                left, right = _split_sides(line)

                # --- line score (two abbrev rows: innings + R H E) ---
                if mode == "linescore":
                    toks = left + right
                    # Team rows start with an abbreviation (non-numeric); this
                    # skips the "1 2 3 4 5 6 R H E" column header (starts with 1).
                    if toks and not _is_int(toks[0]):
                        nums = [int(t) for t in toks if _is_int(t)]
                        if len(nums) >= 4:  # innings... R H E
                            innings = nums[:-3]
                            team_e = nums[-1]
                            if not card.away_innings:
                                card.away_innings = innings
                                card.away_team_e = team_e
                            else:
                                card.home_innings = innings
                                card.home_team_e = team_e
                    continue

                # --- batting rows + annotations ---
                if mode == "batting":
                    away_done = _consume_batting(left, card.away_players, "L", bat_anno, away_done, card, "away")
                    home_done = _consume_batting(right, card.home_players, "R", bat_anno, home_done, card, "home")
                    continue

                # --- pitching rows + annotations ---
                if mode == "pitching":
                    _consume_pitching(left, card.away_players, "L", pit_anno)
                    _consume_pitching(right, card.home_players, "R", pit_anno)
                    continue

    if not card.away_team and not card.home_team:
        return None

    _apply_annotations(card.away_players, bat_anno["L"], pit_anno["L"])
    _apply_annotations(card.home_players, bat_anno["R"], pit_anno["R"])
    card.away_lob = _first_int(_split_labeled(bat_anno["L"]).get("LOB", ""))
    card.home_lob = _first_int(_split_labeled(bat_anno["R"]).get("LOB", ""))
    return card


def _consume_batting(tokens, players, side, anno, done, card, which) -> bool:
    """Process one side of a batting line; returns updated 'done' flag."""
    if not tokens:
        return done
    if tokens[0] == "Totals":
        nums = [t for t in tokens if _is_int(t)]
        if len(nums) >= 6:
            keys = ["ab", "r", "h", "rbi", "bb", "so"]
            totals = dict(zip(keys, [int(x) for x in nums[:6]]))
            if which == "away":
                card.away_totals = totals
            else:
                card.home_totals = totals
        return True
    parsed = _parse_stat_row(tokens, 6)
    if parsed and not done:
        name, pos, nums = parsed
        players.append(
            PlayerStat(
                name=name, position=pos,
                ab=int(nums[0]), r=int(nums[1]), h=int(nums[2]),
                rbi=int(nums[3]), bb=int(nums[4]), so=int(nums[5]),
            )
        )
    else:
        anno[side] += " " + " ".join(tokens)
    return done


def _consume_pitching(tokens, players, side, anno) -> None:
    """Process one side of a pitching line."""
    if not tokens:
        return
    if tokens[0] == "Totals":
        return
    parsed = _parse_stat_row(tokens, 7)
    if parsed:
        name, _pos, nums = parsed
        target = _match(name, players) or _append_new(players, name)
        target.ip = float(nums[0])
        target.p_h = int(nums[1])
        target.p_r = int(nums[2])
        target.er = int(nums[3])
        target.p_bb = int(nums[4])
        target.p_so = int(nums[5])
        target.p_hr = int(nums[6])
    else:
        anno[side] += " " + " ".join(tokens)


def _append_new(players: list[PlayerStat], name: str) -> PlayerStat:
    p = PlayerStat(name=name)
    players.append(p)
    return p


def _apply_annotations(players: list[PlayerStat], bat_blob: str, pit_blob: str) -> None:
    """Distribute 2B/3B/HR (batting) and E (pitching) onto player rows."""
    bat = _split_labeled(bat_blob)
    for label, attr in [("2B", "doubles"), ("3B", "triples"), ("HR", "hr")]:
        for name, count in _name_counts(bat.get(label, "")):
            p = _match(name, players)
            if p:
                setattr(p, attr, getattr(p, attr) + count)
    for name, count in _name_counts(_split_labeled(pit_blob).get("E", "")):
        p = _match(name, players) or _append_new(players, name)
        p.errors += count
