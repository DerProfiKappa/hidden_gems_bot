import heapq
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


Coord = Tuple[int, int]


def manhattan(a: Coord, b: Coord) -> int:
    """Rückgabe der Manhattan-Distanz zweier Punkte."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class AStarPathfinder:
    """A*-Suche und Hilfsfunktionen für das Hidden-Gems-Gitter."""

    DIRECTIONS: Sequence[Tuple[int, int]] = ((0, -1), (1, 0), (0, 1), (-1, 0))

    def __init__(self):
        self.width = 0
        self.height = 0

    def update_bounds(self, width: int, height: int) -> None:
        self.width = max(0, int(width))
        self.height = max(0, int(height))

    def in_bounds(self, pos: Coord) -> bool:
        if self.width <= 0 or self.height <= 0:
            return True
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def _is_walkable(
        self,
        pos: Coord,
        walls: Iterable[Coord],
        known_floor: Optional[Iterable[Coord]],
        allow_unknown: bool,
        goal: Optional[Coord] = None,
    ) -> bool:
        if not self.in_bounds(pos):
            return False
        if walls and pos in walls:
            return False
        if (
            not allow_unknown
            and known_floor is not None
            and pos not in known_floor
            and (goal is None or pos != goal)
        ):
            return False
        return True

    def _step_cost(
        self,
        nxt: Coord,
        visit_count: Optional[Dict[Coord, int]],
        known_floor: Optional[Iterable[Coord]],
        bias: Optional[Dict[str, float]],
    ) -> float:
        """Weiche Strafwerte (Stage-1-Heuristik)."""
        base = 1.0
        if not bias:
            return base
        visit_penalty = bias.get("visit", 0.0)
        unknown_penalty = bias.get("unknown", 0.0)
        if visit_penalty and visit_count:
            visits = min(visit_count.get(nxt, 0), 6)
            base += visits * visit_penalty
        if (
            unknown_penalty
            and known_floor is not None
            and nxt not in known_floor
        ):
            base += unknown_penalty
        return base

    def find_path(
        self,
        start: Coord,
        goal: Coord,
        walls: Iterable[Coord],
        known_floor: Optional[Iterable[Coord]],
        allow_unknown: bool,
        visit_count: Optional[Dict[Coord, int]],
        bias: Optional[Dict[str, float]],
    ) -> Tuple[Optional[List[Coord]], Optional[int], Optional[float]]:
        start = tuple(start)
        goal = tuple(goal)
        if start == goal:
            return [start], 0, 0.0

        open_set: List[Tuple[float, float, Coord]] = []
        heapq.heappush(open_set, (manhattan(start, goal), 0.0, start))
        came_from: Dict[Coord, Optional[Coord]] = {start: None}
        g_score: Dict[Coord, float] = {start: 0.0}

        walls_set = set(walls) if walls else set()
        known_floor_set = set(known_floor) if known_floor else set()
        known_floor_set.add(start)
        known_floor_set.add(goal)

        while open_set:
            f_score, current_g, current = heapq.heappop(open_set)
            if current == goal:
                path = self._reconstruct_path(came_from, current)
                return path, len(path) - 1, current_g
            if current_g > g_score[current]:
                continue
            for dx, dy in self.DIRECTIONS:
                nxt = (current[0] + dx, current[1] + dy)
                if not self._is_walkable(
                    nxt, walls_set, known_floor_set, allow_unknown, goal
                ):
                    continue
                step = self._step_cost(nxt, visit_count, known_floor_set, bias)
                new_g = current_g + step
                if nxt not in g_score or new_g < g_score[nxt]:
                    g_score[nxt] = new_g
                    priority = new_g + manhattan(nxt, goal)
                    came_from[nxt] = current
                    heapq.heappush(open_set, (priority, new_g, nxt))
        return None, None, None

    def build_distance_tree(
        self,
        start: Coord,
        walls: Iterable[Coord],
        known_floor: Optional[Iterable[Coord]],
        allow_unknown: bool,
    ) -> Tuple[Dict[Coord, Optional[Coord]], Dict[Coord, int]]:
        """Dijkstra (ohne Heuristik) für Mehrziel-Abfragen."""
        start = tuple(start)
        queue: List[Tuple[int, Coord]] = [(0, start)]
        prev: Dict[Coord, Optional[Coord]] = {start: None}
        dist: Dict[Coord, int] = {start: 0}

        walls_set = set(walls) if walls else set()
        known_floor_set = set(known_floor) if known_floor else set()
        known_floor_set.add(start)

        while queue:
            cost, current = heapq.heappop(queue)
            if cost != dist[current]:
                continue
            for dx, dy in self.DIRECTIONS:
                nxt = (current[0] + dx, current[1] + dy)
                if not self._is_walkable(
                    nxt, walls_set, known_floor_set, allow_unknown
                ):
                    continue
                new_cost = cost + 1
                if nxt not in dist or new_cost < dist[nxt]:
                    dist[nxt] = new_cost
                    prev[nxt] = current
                    heapq.heappush(queue, (new_cost, nxt))
        return prev, dist

    @staticmethod
    def _reconstruct_path(
        came_from: Dict[Coord, Optional[Coord]], current: Coord
    ) -> List[Coord]:
        path = [current]
        while came_from[current] is not None:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path
