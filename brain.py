from collections import deque
import random
from maps import MapState
from pathfinding import AStarPathfinder


def strecke(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class Brain:
    def __init__(self):
        self.width = 0
        self.height = 0
        self.besuchte_felder = set()
        self.hat_wand_gesehen = False
        self.bekannte_gems = {}
        self.center = None
        self.frontier_felder = set()
        self.RICHTUNG = [
            ('N', (0, -1)),
            ('E', (1, 0)),
            ('S', (0, 1)),
            ('W', (-1, 0))
        ]
        self.DIR_MAP = dict(self.RICHTUNG)
        self.DELTA_TO_DIR = {delta: name for name, delta in self.RICHTUNG}
        self.plan = []
        self.geplantes_ziel = None
        self.geplanter_gem = None
        self.erwartete_pos = None
        self.geplante_reisezeit = None
        self.bekannte_waende = set()
        self.bekannter_boden = set()
        self.unbesuchte_felder = set()
        self.max_kombi = 4
        self.stage_max_gems = 0
        self.full_map_sicht = False
        # kurze Historie gegen Hin-und-her-Flackern
        self.pos_history = deque(maxlen=6)
        self.visit_count = {}
        self.recent_explore_targets = deque(maxlen=60)
        self.aktuelles_explore_ziel = None
        self.alle_floors = set()
        self.idle_spot = None
        self.full_map_sicht = False
        self.occlusion = False
        self.stage_key = None
        self.generator = None
        self.mode = 'default'
        self.map_fully_known = False
        self.graph_center = None
        self.patrol_points = []
        self.patrol_index = 0
        self.rng = random.Random()
        self.prev_cache_known = None
        self.dist_cache_known = None
        self.prev_cache_unknown = None
        self.dist_cache_unknown = None
        self.cache_origin = None
        self.cache_walls_size = None
        self.gem_stats = {}
        self.heat_recent_window = 200
        self.aktuelles_heat_ziel = None
        self.last_tick = -1
        self.map = MapState(
            visited_ref=self.besuchte_felder,
            walls_ref=self.bekannte_waende,
            floor_ref=self.bekannter_boden,
            unvisited_ref=self.unbesuchte_felder,
            frontier_ref=self.frontier_felder,
            visit_count_ref=self.visit_count
        )
        self.pathfinder = AStarPathfinder()
        # A*-Gewichte: Stage 1 bevorzugt neue Felder, meidet Sackgassen.
        self.path_bias_default = {"visit": 0.06, "unknown": 0.35}
        self.path_bias_known = {"visit": 0.04, "unknown": 0.0}
        self.path_bias_explore = {"visit": 0.05, "unknown": 0.25}

    def update_config(self, width, height, seed, config=None):
        self.width = width
        self.height = height
        self.pathfinder.update_bounds(width, height)
        self.hat_wand_gesehen = False
        self.besuchte_felder.clear()
        self.bekannte_gems.clear()
        self.bekannte_waende.clear()
        self.bekannter_boden.clear()
        self.frontier_felder.clear()
        self.unbesuchte_felder.clear()
        self.visit_count.clear()
        self.recent_explore_targets.clear()
        self.aktuelles_explore_ziel = None
        self.alle_floors.clear()
        self.idle_spot = None
        self.map_fully_known = False
        self.graph_center = None
        self.patrol_points = []
        self.patrol_index = 0
        self.mode = 'default'
        self.stage_key = None
        self.generator = None
        self.prev_cache_known = None
        self.dist_cache_known = None
        self.prev_cache_unknown = None
        self.dist_cache_unknown = None
        self.cache_origin = None
        self.cache_walls_size = None
        try:
            self.rng.seed(seed)
        except Exception:
            self.rng.seed(0)
        self.map.update_config(width, height)
        # Unvisited im vorhandenen Set belassen (Referenz in MapState!), nur Inhalte anpassen.
        self.unbesuchte_felder.clear()
        if width > 0 and height > 0:
            x = max(1, min(width - 2, width // 2))
            y = max(1, min(height - 2, height // 2))
            self.center = (x, y)
        if config:
            self.stage_key = config.get("stage_key")
            self.generator = config.get("generator", self.generator)
            self.occlusion = (self.generator != 'arena')
            self.stage_max_gems = config.get("max_gems", self.stage_max_gems)
            vis = config.get("vis_radius")
            if vis is not None and max(self.width, self.height) > 0:
                self.full_map_sicht = (vis >= max(self.width, self.height))
            else:
                self.full_map_sicht = False
            if self.stage_max_gems and self.stage_max_gems <= 1:
                self.max_kombi = 1
                if self.full_map_sicht:
                    self.mode = 'full_map_single_gem'
                else:
                    self.mode = 'single_patrol'
        # MapState-Referenz behalten
        self.map.unvisited = self.unbesuchte_felder
        self.reset_plan()

    def im_feld(self, x, y):
        if self.width <= 0 or self.height <= 0:
            return True
        return 0 <= x < self.width and 0 <= y < self.height

    def mark_visited(self, pos):
        self.map.mark_visited(pos)

    def aktualisiere_umgebung(self, bot_pos, walls, floors):
        if walls:
            self.hat_wand_gesehen = True
        self.map.update_environment(bot_pos, walls, floors, self.DIR_MAP.values())
        if self.full_map_sicht and floors:
            # komplette Karte sichtbar -> alle Bodenfelder merken
            self.alle_floors.update(floors)
            if self.idle_spot is None and self.alle_floors:
                self.idle_spot = self.find_idle_spot()
        # Bei unbekannter Karte: sobald genug Boden bekannt ist, wähle einen Median-Idle-Spot
        if not self.full_map_sicht and self.idle_spot is None:
            if len(self.bekannter_boden) >= max(20, (self.width * self.height) // 10):
                self.idle_spot = self.find_idle_spot_partial()
        self.pruefe_map_komplett()

    def kombi_walls(self, walls):
        return self.map.kombi_walls(walls)

    def zaehle_unbekannte_nachbarn(self, feld):
        return self.map.zaehle_unbekannte_nachbarn(feld, self.DIR_MAP.values())

    def aktualisiere_frontier(self):
        self.map.aktualisiere_frontier(self.DIR_MAP.values())

    def pruefe_map_komplett(self):
        if self.map_fully_known:
            return
        if self.width <= 0 or self.height <= 0:
            return
        bekannte_tiles = self.bekannter_boden.union(self.bekannte_waende)
        if len(bekannte_tiles) >= self.width * self.height:
            self.map_fully_known = True
            ziel = self.find_graph_center(self.bekannte_waende)
            if ziel:
                self.graph_center = ziel
                self.idle_spot = ziel
            self.prepare_patrol_points(force=True)

    def prepare_patrol_points(self, force=False):
        if self.mode not in ('full_map_single_gem', 'single_patrol'):
            self.patrol_points = []
            self.patrol_index = 0
            return
        if not self.map_fully_known and not force:
            return
        basis = self.alle_floors if self.alle_floors else self.bekannter_boden
        if not basis:
            self.patrol_points = []
            self.patrol_index = 0
            return
        start = self.graph_center or self.idle_spot or self.center
        if not start:
            start = next(iter(basis))
        dist = self.distance_map(start, self.bekannte_waende, scope=basis)
        if not dist:
            self.patrol_points = [start]
            self.patrol_index = 0
            return
        kandidaten = [p for p in basis if p in dist]
        if not kandidaten:
            self.patrol_points = [start]
            self.patrol_index = 0
            return
        kandidaten.sort(key=lambda p: (dist[p], p[0], p[1]), reverse=True)
        route = [start]
        if self.mode == 'full_map_single_gem':
            ziel_count = 4
        else:
            ziel_count = 6
        for punkt in kandidaten[:ziel_count]:
            if punkt not in route:
                route.append(punkt)
        self.patrol_points = route
        self.patrol_index = 0

    def sollte_patrouillieren(self, sichtbare_gems):
        if self.mode not in ('full_map_single_gem', 'single_patrol'):
            return False
        if not self.map_fully_known:
            return False
        if sichtbare_gems or self.bekannte_gems:
            return False
        return bool(self.patrol_points)

    def patrol_move(self, bot_pos, walls):
        if not self.patrol_points:
            return 'WAIT'
        versuche = len(self.patrol_points)
        while versuche > 0:
            ziel = self.patrol_points[self.patrol_index % len(self.patrol_points)]
            if tuple(bot_pos) == ziel:
                self.patrol_index = (self.patrol_index + 1) % len(self.patrol_points)
                versuche -= 1
                continue
            pfad, dist, _ = self.astar_path(
                bot_pos, ziel, walls, allow_unknown=False, bias=self.path_bias_known
            )
            if pfad and len(pfad) > 1:
                naechster = pfad[1]
                delta = (naechster[0] - bot_pos[0], naechster[1] - bot_pos[1])
                richtung = self.DELTA_TO_DIR.get(delta)
                if richtung:
                    self.erwartete_pos = naechster
                    return richtung
            self.patrol_index = (self.patrol_index + 1) % len(self.patrol_points)
            versuche -= 1
        return 'WAIT'

    def reset_plan(self):
        self.plan = []
        self.geplantes_ziel = None
        self.geplanter_gem = None
        self.erwartete_pos = None
        self.geplante_reisezeit = None
        # self.aktuelles_explore_ziel = None

    def aktualisiere_gems(self, bot_pos, sichtbare_gems):
        bot_pos = tuple(bot_pos)
        neue_cache = {}

        for pos, ttl in self.bekannte_gems.items():
            rest = ttl - 1
            if rest > 0 and pos != bot_pos:
                neue_cache[pos] = rest

        for gem in sichtbare_gems:
            position = tuple(gem.get("position", []))
            ttl_roh = gem.get("ttl")
            if position and ttl_roh is not None:
                try:
                    ttl = int(ttl_roh)
                except (TypeError, ValueError):
                    continue
                neue_cache[position] = ttl

        self.bekannte_gems = neue_cache
        # if not sichtbare_gems:
        #    self.aktuelles_explore_ziel = None

    def manhattan_path(self, start, ziel):
        pfad = [tuple(start)]
        x, y = start
        zx, zy = ziel

        if x != zx:
            schritt_x = 1 if zx > x else -1
            while x != zx:
                x += schritt_x
                if not self.im_feld(x, y):
                    return None
                pfad.append((x, y))

        if y != zy:
            schritt_y = 1 if zy > y else -1
            while y != zy:
                y += schritt_y
                if not self.im_feld(x, y):
                    return None
                pfad.append((x, y))

        return pfad

    def astar_path(self, start, ziel, walls, allow_unknown=True, bias=None):
        """Wickelt die A*-Suche inkl. Stage-1-Bias ab."""
        pfad, dist, kosten = self.pathfinder.find_path(
            start=start,
            goal=ziel,
            walls=walls,
            known_floor=self.bekannter_boden,
            allow_unknown=allow_unknown,
            visit_count=self.visit_count,
            bias=bias or self.path_bias_default
        )
        return pfad, dist, kosten

    def pfad_zu_moves(self, pfad):
        moves = []
        if not pfad:
            return moves
        for prev, curr in zip(pfad, pfad[1:]):
            delta = (curr[0] - prev[0], curr[1] - prev[1])
            richtung = self.DELTA_TO_DIR.get(delta)
            if richtung is None:
                continue
            moves.append((richtung, curr))
        return moves

    def choose_target(self, bot_pos, walls):
        if walls:
            self.hat_wand_gesehen = True

        if not self.bekannte_gems:
            return None, None, None, None

        pfad_cache = {}

        def hole_pfad(start, ziel):
            s = tuple(start)
            z = tuple(ziel)
            key = (s, z)
            if key in pfad_cache:
                return pfad_cache[key]
            pfad, dist, _ = self.astar_path(
                s, z, walls, allow_unknown=False, bias=self.path_bias_known
            )
            if not pfad:
                pfad, dist, _ = self.astar_path(
                    s, z, walls, allow_unknown=True, bias=self.path_bias_default
                )
            if pfad:
                pfad_cache[key] = (pfad, dist)
                rev = list(reversed(pfad))
                pfad_cache[(z, s)] = (rev, dist)
            else:
                pfad_cache[key] = (None, None)
            return pfad_cache[key]

        def route_besser(neu, alt):
            if alt is None:
                return True
            rneu = neu[0] / max(1, neu[1])
            ralt = alt[0] / max(1, alt[1])
            if rneu != ralt:
                return rneu > ralt
            if neu[0] != alt[0]:
                return neu[0] > alt[0]
            if neu[1] != alt[1]:
                return neu[1] < alt[1]
            return neu[2] > alt[2]

        def suche_route(start, rest_map, score, zeit, tiefe):
            beste = (score, zeit, tiefe)
            if tiefe >= self.max_kombi or not rest_map:
                return beste
            for pos2, ttl2 in rest_map.items():
                pfad2, dist2 = hole_pfad(start, pos2)
                if not pfad2:
                    continue
                arrival2 = ttl2 - dist2
                if arrival2 <= 0:
                    continue
                neue_rest = {}
                for pos3, ttl3 in rest_map.items():
                    if pos3 == pos2:
                        continue
                    rest_ttl = ttl3 - dist2
                    if rest_ttl > 0:
                        neue_rest[pos3] = rest_ttl
                kandidat = suche_route(pos2, neue_rest, score + arrival2, zeit + dist2, tiefe + 1)
                if route_besser(kandidat, beste):
                    beste = kandidat
            return beste

        kandidaten = sorted(self.bekannte_gems.items(), key=lambda item: (-item[1], strecke(bot_pos, item[0])))
        kandidaten = kandidaten[:8]
        beste_wahl = None

        if self.stage_max_gems <= 1:
            # einfach: nimm den erreichbaren Gem mit kürzester Distanz
            for position, ttl in kandidaten:
                if ttl <= 0:
                    continue
                pfad, dist = hole_pfad(bot_pos, position)
                if not pfad:
                    continue
                arrival_ttl = ttl - dist
                if arrival_ttl <= 0:
                    continue
                wertung = (dist, -arrival_ttl, position)
                if beste_wahl is None or wertung < beste_wahl[0]:
                    bestes_gem = {"position": list(position), "ttl": arrival_ttl}
                    beste_wahl = (wertung, bestes_gem, pfad, dist)
            if beste_wahl is None:
                return None, None, None, None
            _, bestes_gem, pfad, reisezeit = beste_wahl
            return tuple(bestes_gem["position"]), bestes_gem, pfad, reisezeit

        for position, ttl in kandidaten:
            if ttl <= 0:
                continue
            pfad, dist = hole_pfad(bot_pos, position)
            if not pfad:
                continue
            arrival_ttl = ttl - dist
            if arrival_ttl <= 0:
                continue

            rest_map = {}
            for pos2, ttl2 in self.bekannte_gems.items():
                if pos2 == position:
                    continue
                neu_ttl = ttl2 - dist
                if neu_ttl > 0:
                    rest_map[pos2] = neu_ttl

            kombi = suche_route(position, rest_map, arrival_ttl, dist, 1)
            kombi_score, kombi_zeit, kombi_tiefe = kombi
            zeit = max(1, kombi_zeit)
            effizienz = kombi_score / zeit

            wertung = (-effizienz, -kombi_score, kombi_zeit, -arrival_ttl, dist, -kombi_tiefe, position)
            if beste_wahl is None or wertung < beste_wahl[0]:
                bestes_gem = {"position": list(position), "ttl": arrival_ttl}
                beste_wahl = (wertung, bestes_gem, pfad, dist)

        if beste_wahl is None:
            return None, None, None, None

        _, bestes_gem, pfad, reisezeit = beste_wahl
        return tuple(bestes_gem["position"]), bestes_gem, pfad, reisezeit

    def build_distance_tree(self, start, walls, allow_unknown):
        bekannte_tiles = self.bekannter_boden if self.bekannter_boden else {tuple(start)}
        return self.pathfinder.build_distance_tree(start, walls, bekannte_tiles, allow_unknown)

    def pfad_aus_prev(self, prev, start, ziel):
        if ziel not in prev:
            return None
        pfad = []
        cur = ziel
        while cur is not None:
            pfad.append(cur)
            cur = prev[cur]
        pfad.reverse()
        if pfad and pfad[0] == tuple(start):
            return pfad
        return None

    def prepare_distance_cache(self, bot_pos, walls):
        walls_size = len(walls)
        if self.cache_origin == tuple(bot_pos) and self.cache_walls_size == walls_size:
            return
        self.cache_origin = tuple(bot_pos)
        self.cache_walls_size = walls_size
        self.prev_cache_known, self.dist_cache_known = self.build_distance_tree(bot_pos, walls, allow_unknown=False)
        self.prev_cache_unknown, self.dist_cache_unknown = self.build_distance_tree(bot_pos, walls, allow_unknown=True)

    def greedy_towards(self, bot_pos, ziel, walls):
        bx, by = bot_pos
        zx, zy = ziel
        beste = None
        for name, (dx, dy) in self.RICHTUNG:
            nx = bx + dx
            ny = by + dy
            if not self.im_feld(nx, ny):
                continue
            if (nx, ny) in walls:
                continue
            dist = strecke((nx, ny), (zx, zy))
            besuche = self.visit_count.get((nx, ny), 0)
            wert = (dist, besuche, name)
            if beste is None or wert < beste[0]:
                beste = (wert, name, (nx, ny))
        if beste:
            return beste[1], beste[2]
        return None, None

    def find_idle_spot(self):
        # wähle Bodenfeld nahe am Median, damit durchschnittliche Weglänge zu Spawns klein ist
        xs = [p[0] for p in self.alle_floors]
        ys = [p[1] for p in self.alle_floors]
        if not xs or not ys:
            return self.center
        xs_sorted = sorted(xs)
        ys_sorted = sorted(ys)
        mx = xs_sorted[len(xs_sorted) // 2]
        my = ys_sorted[len(ys_sorted) // 2]
        kandidat = (mx, my)
        if kandidat in self.alle_floors:
            return kandidat
        # falls Median auf Wand liegt (sollte selten sein), nimm nächstgelegenes Bodenfeld
        beste = None
        for p in self.alle_floors:
            d = strecke(kandidat, p)
            if beste is None or d < beste[0]:
                beste = (d, p)
        return beste[1] if beste else self.center

    def find_idle_spot_partial(self):
        if not self.bekannter_boden:
            return self.center
        xs = [p[0] for p in self.bekannter_boden]
        ys = [p[1] for p in self.bekannter_boden]
        xs_sorted = sorted(xs)
        ys_sorted = sorted(ys)
        mx = xs_sorted[len(xs_sorted) // 2]
        my = ys_sorted[len(ys_sorted) // 2]
        kandidat = (mx, my)
        if kandidat in self.bekannter_boden:
            return kandidat
        beste = None
        for p in self.bekannter_boden:
            d = strecke(kandidat, p)
            if beste is None or d < beste[0]:
                beste = (d, p)
        return beste[1] if beste else self.center

    def distance_map(self, start, walls, scope=None):
        ziel_floors = scope if scope else self.bekannter_boden
        bekannte_tiles = ziel_floors if ziel_floors else {tuple(start)}
        _, dist = self.pathfinder.build_distance_tree(start, walls, bekannte_tiles, allow_unknown=False)
        return dist

    def find_graph_center(self, walls):
        if not self.alle_floors:
            return self.center
        floors = list(self.alle_floors)
        best = None
        best_val = None
        for tile in floors:
            dist = self.distance_map(tile, walls, scope=self.alle_floors)
            if len(dist) < len(floors):
                continue
            maxd = max(dist.values())
            avgd = sum(dist.values()) / len(dist)
            val = (maxd, avgd)
            if best_val is None or val < best_val:
                best_val = val
                best = tile
        return best if best else self.center

    def idle_move(self, bot_pos, walls):
        zielpunkt = self.idle_spot or self.center
        if not zielpunkt:
            return 'WAIT'

        cx, cy = zielpunkt
        bx, by = bot_pos
        kandidaten = []

        if bx < cx:
            kandidaten.append('E')
        elif bx > cx:
            kandidaten.append('W')

        if by < cy:
            kandidaten.append('S')
        elif by > cy:
            kandidaten.append('N')

        for name in kandidaten:
            dx, dy = self.DIR_MAP[name]
            nx = bx + dx
            ny = by + dy
            if self.im_feld(nx, ny) and (nx, ny) not in walls:
                return name

        pfad, dist, _ = self.astar_path(
            bot_pos, zielpunkt, walls, allow_unknown=False, bias=self.path_bias_known
        )
        if pfad and len(pfad) > 1:
            naechster = pfad[1]
            delta = (naechster[0] - bot_pos[0], naechster[1] - bot_pos[1])
            richtung = self.DELTA_TO_DIR.get(delta)
            if richtung:
                return richtung

        return 'WAIT'

    def stelle_plan_sicher(self, bot_pos, walls, gems):
        # Einfach: nimm den nächsten sichtbaren Gem und plane den direkten Weg.
        self.reset_plan()

        if not gems and not self.bekannte_gems:
            return None, None, None

        ziel, bestes_gem, pfad, reisezeit = self.choose_target(bot_pos, walls)
        if not pfad:
            if ziel:
                schritt, nxt = self.greedy_towards(bot_pos, ziel, walls)
                if schritt:
                    self.plan = [(schritt, nxt)]
                    self.geplantes_ziel = ziel
                    self.geplanter_gem = bestes_gem
                    self.geplante_reisezeit = None
                    self.erwartete_pos = None
                    return self.geplantes_ziel, self.geplanter_gem, self.geplante_reisezeit
            return None, None, None

        self.plan = self.pfad_zu_moves(pfad)
        self.geplantes_ziel = ziel
        self.geplanter_gem = bestes_gem
        self.geplante_reisezeit = reisezeit
        self.erwartete_pos = None

        return self.geplantes_ziel, self.geplanter_gem, self.geplante_reisezeit

    def next_move(self, bot_pos, walls, floors, gems):
        # falls letzter Schritt blockiert war -> als Wand merken und neu planen
        if self.erwartete_pos and tuple(bot_pos) != tuple(self.erwartete_pos):
            self.bekannte_waende.add(tuple(self.erwartete_pos))
            self.hat_wand_gesehen = True
            self.reset_plan()
            self.aktuelles_explore_ziel = None

        # Positions-Historie und Kreisbrecher
        self.pos_history.append(tuple(bot_pos))
        if len(self.pos_history) == self.pos_history.maxlen and len(set(self.pos_history)) <= 2:
            for p in set(self.pos_history):
                self.visit_count[p] = self.visit_count.get(p, 0) + 2
            self.reset_plan()
            self.aktuelles_explore_ziel = None

        self.aktualisiere_umgebung(bot_pos, walls, floors)
        alle_walls = self.kombi_walls(walls)
        self.aktualisiere_gems(bot_pos, gems)

        ziel, gem, reisezeit = self.stelle_plan_sicher(bot_pos, alle_walls, gems)

        # Gem bekannt, aber kein Plan? Dann trotzdem Schritt in Richtung Gem erzwingen.
        if not self.plan and gem and ziel:
            greedy_move, nxt = self.greedy_towards(bot_pos, ziel, alle_walls)
            if greedy_move:
                self.erwartete_pos = nxt
                return greedy_move, ziel, gem, reisezeit, 0

        # Wenn wir 2 Ticks auf derselben Stelle stehen -> Plan verwerfen und zwingend explorieren
        if len(self.pos_history) >= 2 and self.pos_history[-1] == self.pos_history[-2]:
            if walls:
                self.bekannte_waende.intersection_update(walls)
            self.reset_plan()
            self.aktuelles_explore_ziel = None
            force = self.explore_move(bot_pos, set(walls))
            if force != 'WAIT':
                dx, dy = self.DIR_MAP[force]
                self.erwartete_pos = (bot_pos[0] + dx, bot_pos[1] + dy)
                return force, ziel, gem, reisezeit, 0

        if not self.plan:
            if self.sollte_patrouillieren(gems):
                patrol = self.patrol_move(bot_pos, alle_walls)
                if patrol != 'WAIT':
                    dx, dy = self.DIR_MAP[patrol]
                    self.erwartete_pos = (bot_pos[0] + dx, bot_pos[1] + dy)
                else:
                    self.erwartete_pos = tuple(bot_pos)
                return patrol, ziel, gem, reisezeit, 0
            explore = self.explore_move(bot_pos, alle_walls)
            if explore != 'WAIT':
                dx, dy = self.DIR_MAP[explore]
                self.erwartete_pos = (bot_pos[0] + dx, bot_pos[1] + dy)
                return explore, ziel, gem, reisezeit, 0

            idle = self.idle_move(bot_pos, alle_walls)
            if idle != 'WAIT':
                dx, dy = self.DIR_MAP[idle]
                self.erwartete_pos = (bot_pos[0] + dx, bot_pos[1] + dy)
            else:
                self.erwartete_pos = tuple(bot_pos)
            return idle, ziel, gem, reisezeit, 0

        if self.plan and self.plan[0][1] in alle_walls:
            ziel, gem, reisezeit = self.stelle_plan_sicher(bot_pos, alle_walls, gems)
            if not self.plan or (self.plan and self.plan[0][1] in alle_walls):
                ausweich = self.explore_move(bot_pos, alle_walls)
                return ausweich, ziel, gem, reisezeit, 0

        richtung, naechster = self.plan.pop(0)
        self.erwartete_pos = naechster
        rest = len(self.plan)
        return richtung, ziel, gem, reisezeit, rest

    def explore_move(self, bot_pos, walls):
        alle_walls = self.kombi_walls(walls)
        # BFS einmal pro Tick vorbereiten, damit wir das Soft-Limit nicht reißen
        self.prepare_distance_cache(bot_pos, alle_walls)
        prev_known = self.prev_cache_known
        dist_known = self.dist_cache_known
        prev_unknown = self.prev_cache_unknown
        dist_unknown = self.dist_cache_unknown

        # 0) aktives Explorationsziel weiterverfolgen, falls erreichbar
        if self.aktuelles_explore_ziel:
            pfad = self.pfad_aus_prev(prev_known, bot_pos, self.aktuelles_explore_ziel)
            if not pfad:
                # Falls Ziel im Nebel liegt (Unseen), versuche es über unbekanntes Terrain
                pfad = self.pfad_aus_prev(prev_unknown, bot_pos, self.aktuelles_explore_ziel)
            
            if pfad and len(pfad) > 1:
                naechster = pfad[1]
                delta = (naechster[0] - bot_pos[0], naechster[1] - bot_pos[1])
                richtung = self.DELTA_TO_DIR.get(delta)
                if richtung:
                    self.erwartete_pos = naechster
                    return richtung
            else:
                self.aktuelles_explore_ziel = None

        kandidaten_frontier = []
        if self.frontier_felder:
            ziel_liste = sorted(
                self.frontier_felder,
                key=lambda pos: (
                    self.visit_count.get(pos, 0),
                    dist_known.get(pos, strecke(bot_pos, pos)),
                    -self.zaehle_unbekannte_nachbarn(pos),
                    pos[1],
                    pos[0],
                )
            )
            for ziel in ziel_liste:
                if ziel in self.recent_explore_targets:
                    continue
                if ziel not in dist_known:
                    continue
                dist = dist_known[ziel]
                unbekannte = self.zaehle_unbekannte_nachbarn(ziel)
                odw = self.visit_count.get(ziel, 0)
                jitter = 0.0 if self.mode == 'full_map_single_gem' else self.rng.random() * 0.5
                # Weighted Frontier Search: Distance - (Unknown_Neighbors * 1.0)
                score = dist - (unbekannte * 1.0) + (odw * 2.0) + jitter
                wertung = (score, -unbekannte, odw, ziel)
                kandidaten_frontier.append(wertung)

        kandidaten_unvisited = []
        if self.unbesuchte_felder and not self.full_map_sicht:
            ziel_unv = sorted(
                self.unbesuchte_felder,
                key=lambda pos: (
                    self.visit_count.get(pos, 0),
                    dist_unknown.get(pos, strecke(bot_pos, pos)),
                    pos[1],
                    pos[0],
                )
            )
            for ziel in ziel_unv:
                if ziel in self.recent_explore_targets:
                    continue
                if ziel not in dist_unknown:
                    continue
                dist = dist_unknown[ziel]
                odw = self.visit_count.get(ziel, 0)
                jitter = 0.0 if self.mode == 'full_map_single_gem' else self.rng.random() * 0.5
                wertung = (dist + odw * 2 + jitter, odw, ziel)
                kandidaten_unvisited.append(wertung)

        ziel_pfadrichtung = None
        if kandidaten_frontier:
            kandidaten_frontier.sort()
            _, _, _, ziel = kandidaten_frontier[0]
            ziel_pfadrichtung = (ziel, prev_known)
        elif kandidaten_unvisited:
            kandidaten_unvisited.sort()
            _, _, ziel = kandidaten_unvisited[0]
            ziel_pfadrichtung = (ziel, prev_unknown)

        if ziel_pfadrichtung:
            ziel, prev_map = ziel_pfadrichtung
            pfad = self.pfad_aus_prev(prev_map, bot_pos, ziel)
            self.aktuelles_explore_ziel = ziel
            self.recent_explore_targets.append(ziel)
            naechster = pfad[1]
            delta = (naechster[0] - bot_pos[0], naechster[1] - bot_pos[1])
            richtung = self.DELTA_TO_DIR.get(delta)
            if richtung:
                self.erwartete_pos = naechster
                return richtung

        # 3) Es gibt noch unbekannte Koordinaten (nicht gesehen, nicht als Wand): dorthin laufen.
        if self.width > 0 and self.height > 0:
            unseen = []
            for pos, dist in dist_unknown.items():
                if pos in self.bekannter_boden or pos in alle_walls:
                    continue
                if pos in self.recent_explore_targets:
                    continue
                unseen.append((dist, pos))
            if unseen:
                if self.mode == 'full_map_single_gem':
                    unseen.sort(key=lambda item: (item[0], item[1][1], item[1][0]))
                else:
                    self.rng.shuffle(unseen)
                ziel = unseen[0][1]
                pfad = self.pfad_aus_prev(prev_unknown, bot_pos, ziel)
                if pfad and len(pfad) > 1:
                    self.aktuelles_explore_ziel = ziel
                    self.recent_explore_targets.append(ziel)
                    naechster = pfad[1]
                    delta = (naechster[0] - bot_pos[0], naechster[1] - bot_pos[1])
                    richtung = self.DELTA_TO_DIR.get(delta)
                    if richtung:
                        self.erwartete_pos = naechster
                        return richtung

        if self.full_map_sicht and not self.bekannte_gems:
            zielpunkt = self.idle_spot or self.center
            if zielpunkt and tuple(bot_pos) != tuple(zielpunkt):
                pfad_c = None
                if not self.hat_wand_gesehen and not alle_walls:
                    pfad_c = self.manhattan_path(bot_pos, zielpunkt)
                if pfad_c is None:
                    pfad_c, _, _ = self.astar_path(
                        bot_pos, zielpunkt, alle_walls, allow_unknown=True, bias=self.path_bias_default
                    )
                if pfad_c and len(pfad_c) > 1:
                    naechster = pfad_c[1]
                    delta = (naechster[0] - bot_pos[0], naechster[1] - bot_pos[1])
                    richtung = self.DELTA_TO_DIR.get(delta)
                    if richtung:
                        self.erwartete_pos = naechster
                        return richtung
            self.erwartete_pos = tuple(bot_pos)
            return 'WAIT'

        if self.unbesuchte_felder:
            beste = None
            for ziel in self.unbesuchte_felder:
                if ziel in self.recent_explore_targets:
                    continue
                pfad, _, _ = self.astar_path(
                    bot_pos, ziel, alle_walls, allow_unknown=True, bias=self.path_bias_explore
                )
                if not pfad or len(pfad) < 2:
                    continue
                dist = len(pfad) - 1
                wertung = (dist, ziel)
                if beste is None or wertung < beste[0]:
                    beste = (wertung, pfad, ziel)
            if beste:
                naechster = beste[1][1]
                delta = (naechster[0] - bot_pos[0], naechster[1] - bot_pos[1])
                richtung = self.DELTA_TO_DIR.get(delta)
                if richtung:
                    self.recent_explore_targets.append(beste[2])
                    self.erwartete_pos = naechster
                    return richtung

        # Alles bekannt -> Patrouille: am wenigsten besuchte Felder, lieber weiter weg.
        if self.bekannter_boden:
            min_visit = min(self.visit_count.get(pos, 0) for pos in self.bekannter_boden)
            beste_ziel = None
            for ziel in self.bekannter_boden:
                if ziel == tuple(bot_pos):
                    continue
                if ziel in self.recent_explore_targets:
                    continue
                odw = self.visit_count.get(ziel, 0)
                if odw > min_visit:
                    continue
                dist = strecke(bot_pos, ziel)
                wertung = (-dist, ziel)
                if beste_ziel is None or wertung < beste_ziel[0]:
                    beste_ziel = (wertung, ziel)

            if beste_ziel:
                ziel = beste_ziel[1]
                pfad, _, _ = self.astar_path(
                    bot_pos, ziel, alle_walls, allow_unknown=False, bias=self.path_bias_known
                )
                if pfad and len(pfad) > 1:
                    self.aktuelles_explore_ziel = ziel
                    self.recent_explore_targets.append(ziel)
                    naechster = pfad[1]
                    delta = (naechster[0] - bot_pos[0], naechster[1] - bot_pos[1])
                    richtung = self.DELTA_TO_DIR.get(delta)
                    if richtung:
                        self.erwartete_pos = naechster
                        return richtung

        x, y = bot_pos
        kandidaten = []
        prev = self.pos_history[-2] if len(self.pos_history) >= 2 else None
        for name, (dx, dy) in self.DIR_MAP.items():
            nx = x + dx
            ny = y + dy
            if not self.im_feld(nx, ny):
                continue
            if (nx, ny) in alle_walls:
                continue
            count = self.visit_count.get((nx, ny), 0)
            backtrack = 1 if prev and (nx, ny) == prev else 0
            jitter = self.rng.random() * 0.3
            kandidaten.append((count + jitter, backtrack, name, (nx, ny)))
        if kandidaten:
            kandidaten.sort()
            _, _, name, nxt = kandidaten[0]
            self.erwartete_pos = nxt
            return name

        self.erwartete_pos = tuple(bot_pos)
        return 'WAIT'
