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

    def update_environment(self, bot_pos, walls, floors, dir_map_values):
        if walls:
            wand_set = set(walls)
            self.walls.update(wand_set)
            # Falls wir Koordinaten fälschlich als "unbesucht" hatten, hier säubern.
            self.unvisited.difference_update(wand_set)
        sichtbarer_boden = set(floors)
        if sichtbarer_boden:
            self.floor.update(sichtbarer_boden)
            for feld in sichtbarer_boden:
                if feld not in self.visited and feld not in self.walls:
                    self.unvisited.add(feld)
        self.floor.add(tuple(bot_pos))
        self.unvisited.discard(tuple(bot_pos))
        self.aktualisiere_frontier(dir_map_values)

    def kombi_walls(self, fresh_walls):
        mix = set(fresh_walls)
        if self.walls:
            mix.update(self.walls)
        return mix
