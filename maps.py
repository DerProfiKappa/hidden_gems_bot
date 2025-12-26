class MapState:
    """
    Kapselt Boden/Wände/Unvisited/Frontier sowie Besuchszähler.
    Arbeitet über Referenzen auf die vom Brain verwalteten Sets/Dicts.
    """

    def __init__(self, visited_ref, walls_ref, floor_ref, unvisited_ref, frontier_ref, visit_count_ref):
        self.width = 0
        self.height = 0
        self.visited = visited_ref
        self.walls = walls_ref
        self.floor = floor_ref
        self.unvisited = unvisited_ref
        self.frontier = frontier_ref
        self.visit_count = visit_count_ref

    def update_config(self, width, height):
        self.width = width
        self.height = height
        # Unvisited wird nach Sicht-Updates gefüllt
        self.unvisited.clear()
        self.frontier.clear()

    def mark_visited(self, pos):
        punkt = tuple(pos)
        self.visited.add(punkt)
        self.unvisited.discard(punkt)
        self.frontier.discard(punkt)
        self.visit_count[punkt] = self.visit_count.get(punkt, 0) + 1

    def zaehle_unbekannte_nachbarn(self, feld, dir_map_values):
        fx, fy = feld
        unbekannte = 0
        for dx, dy in dir_map_values:
            nx = fx + dx
            ny = fy + dy
            if self.width > 0 and not (0 <= nx < self.width):
                continue
            if self.height > 0 and not (0 <= ny < self.height):
                continue
            nachbar = (nx, ny)
            if nachbar in self.walls:
                continue
            if nachbar in self.floor:
                continue
            unbekannte += 1
        return unbekannte

    def hole_unbekannte_nachbarn(self, feld, dir_map_values):
        fx, fy = feld
        unbekannte = []
        for dx, dy in dir_map_values:
            nx = fx + dx
            ny = fy + dy
            if self.width > 0 and not (0 <= nx < self.width):
                continue
            if self.height > 0 and not (0 <= ny < self.height):
                continue
            nachbar = (nx, ny)
            if nachbar in self.walls:
                continue
            if nachbar in self.floor:
                continue
            unbekannte.append(nachbar)
        return unbekannte

    def aktualisiere_frontier(self, dir_map_values):
        if not self.floor:
            self.frontier.clear()
            return
        neue_frontier = set()
        for feld in self.floor:
            if feld in self.walls:
                continue
            if self.zaehle_unbekannte_nachbarn(feld, dir_map_values) > 0:
                neue_frontier.add(feld)
        self.frontier.clear()
        self.frontier.update(neue_frontier)

    def _has_unbekannt(self, feld, dir_map_values):
        fx, fy = feld
        for dx, dy in dir_map_values:
            nx = fx + dx
            ny = fy + dy
            if self.width > 0 and not (0 <= nx < self.width):
                continue
            if self.height > 0 and not (0 <= ny < self.height):
                continue
            nachbar = (nx, ny)
            if nachbar in self.walls:
                continue
            if nachbar in self.floor:
                continue
            return True
        return False

    def _update_frontier_incremental(self, changed_tiles, dir_map_values):
        if not changed_tiles:
            return
        kandidaten = set()
        for fx, fy in changed_tiles:
            kandidaten.add((fx, fy))
            for dx, dy in dir_map_values:
                nx = fx + dx
                ny = fy + dy
                if self.width > 0 and not (0 <= nx < self.width):
                    continue
                if self.height > 0 and not (0 <= ny < self.height):
                    continue
                kandidaten.add((nx, ny))
        for k in kandidaten:
            if k in self.walls:
                self.frontier.discard(k)
                continue
            if k in self.floor:
                if self._has_unbekannt(k, dir_map_values):
                    self.frontier.add(k)
                else:
                    self.frontier.discard(k)
            else:
                self.frontier.discard(k)

    def update_environment(self, bot_pos, walls, floors, dir_map_values):
        wand_set = set(walls) if walls else set()
        neue_walls = wand_set.difference(self.walls)
        if neue_walls:
            self.walls.update(neue_walls)
            self.unvisited.difference_update(neue_walls)
        sichtbarer_boden = set(floors) if floors else set()
        neue_floors = sichtbarer_boden.difference(self.floor)
        if sichtbarer_boden:
            self.floor.update(sichtbarer_boden)
            for feld in sichtbarer_boden:
                if feld not in self.visited and feld not in self.walls:
                    self.unvisited.add(feld)
        bot_tuple = tuple(bot_pos)
        if bot_tuple not in self.floor:
            neue_floors.add(bot_tuple)
        self.floor.add(bot_tuple)
        self.unvisited.discard(bot_tuple)

        changed = set(neue_walls)
        changed.update(neue_floors)
        if bot_tuple:
            changed.add(bot_tuple)
        self._update_frontier_incremental(changed, dir_map_values)

    def kombi_walls(self, fresh_walls):
        mix = set(fresh_walls)
        if self.walls:
            mix.update(self.walls)
        return mix
