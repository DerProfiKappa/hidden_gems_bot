from collections import deque
import random
from maps import MapState


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
        self.rng = random.Random()
        self.map = MapState(
            visited_ref=self.besuchte_felder,
            walls_ref=self.bekannte_waende,
            floor_ref=self.bekannter_boden,
            unvisited_ref=self.unbesuchte_felder,
            frontier_ref=self.frontier_felder,
            visit_count_ref=self.visit_count
        )

    def update_config(self, width, height, seed, config=None):
        self.width = width
        self.height = height
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
            self.stage_max_gems = config.get("max_gems", self.stage_max_gems)
            vis = config.get("vis_radius")
            if vis is not None and max(self.width, self.height) > 0:
                self.full_map_sicht = (vis >= max(self.width, self.height))
            if self.stage_max_gems and self.stage_max_gems <= 1:
                self.max_kombi = 1
        # MapState-Referenz behalten
        self.map.unvisited = self.unbesuchte_felder

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

    def kombi_walls(self, walls):
        return self.map.kombi_walls(walls)

    def zaehle_unbekannte_nachbarn(self, feld):
        return self.map.zaehle_unbekannte_nachbarn(feld, self.DIR_MAP.values())

    def aktualisiere_frontier(self):
        self.map.aktualisiere_frontier(self.DIR_MAP.values())

    def reset_plan(self):
        self.plan = []
        self.geplantes_ziel = None
        self.geplanter_gem = None
        self.erwartete_pos = None
        self.geplante_reisezeit = None
        self.aktuelles_explore_ziel = None
        self.idle_spot = None

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
        if not sichtbare_gems:
            self.aktuelles_explore_ziel = None

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

    def bfs(self, start, ziel, walls, allow_unknown=True):
        start = tuple(start)
        ziel = tuple(ziel)
        if start == ziel:
            return [start]

        queue = deque([start])
        vorgaenger = {start: None}

        while queue:
            x, y = queue.popleft()
            if (x, y) == ziel:
                break
            for dx, dy in self.DIR_MAP.values():
                nx = x + dx
                ny = y + dy
                nachbar = (nx, ny)
                if nachbar in vorgaenger:
                    continue
                if not self.im_feld(nx, ny):
                    continue
                if nachbar in walls:
                    continue
                if not allow_unknown and (nachbar not in self.bekannter_boden and nachbar != ziel):
                    continue
                vorgaenger[nachbar] = (x, y)
                queue.append(nachbar)

        if ziel not in vorgaenger:
            return None

        pfad = []
        aktueller = ziel
        while aktueller is not None:
            pfad.append(aktueller)
            aktueller = vorgaenger[aktueller]
        pfad.reverse()
        return pfad

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
            key = (tuple(start), tuple(ziel))
            if key in pfad_cache:
                return pfad_cache[key]
            pfad = self.bfs(tuple(start), tuple(ziel), walls, allow_unknown=False)
            if pfad:
                dist = len(pfad) - 1
                pfad_cache[key] = (pfad, dist)
                rev = list(reversed(pfad))
                pfad_cache[(tuple(ziel), tuple(start))] = (rev, dist)
                return pfad_cache[key]
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

    def bfs_all(self, start, walls):
        start = tuple(start)
        queue = deque([start])
        dist = {start: 0}
        while queue:
            x, y = queue.popleft()
            for dx, dy in self.DIR_MAP.values():
                nx = x + dx
                ny = y + dy
                nxt = (nx, ny)
                if nxt in dist:
                    continue
                if nxt in walls:
                    continue
                if self.width > 0 and (nx < 0 or nx >= self.width or ny < 0 or ny >= self.height):
                    continue
                if self.alle_floors and nxt not in self.alle_floors:
                    continue
                dist[nxt] = dist[(x, y)] + 1
                queue.append(nxt)
        return dist

    def find_graph_center(self, walls):
        if not self.alle_floors:
            return self.center
        floors = list(self.alle_floors)
        best = None
        best_val = None
        for tile in floors:
            dist = self.bfs_all(tile, walls)
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
        if not self.center:
            return 'WAIT'

        cx, cy = self.center
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

        return 'WAIT'

    def stelle_plan_sicher(self, bot_pos, walls, gems):
        # Einfach: nimm den nächsten sichtbaren Gem und plane den direkten Weg.
        self.reset_plan()

        if not gems and not self.bekannte_gems:
            return None, None, None

        ziel, bestes_gem, pfad, reisezeit = self.choose_target(bot_pos, walls)
        if not pfad:
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

        # Positions-Historie und Kreisbrecher
        self.pos_history.append(tuple(bot_pos))
        if len(self.pos_history) == self.pos_history.maxlen and len(set(self.pos_history)) <= 2:
            for p in set(self.pos_history):
                self.visit_count[p] = self.visit_count.get(p, 0) + 2
            self.reset_plan()

        self.aktualisiere_umgebung(bot_pos, walls, floors)
        alle_walls = self.kombi_walls(walls)
        self.aktualisiere_gems(bot_pos, gems)

        ziel, gem, reisezeit = self.stelle_plan_sicher(bot_pos, alle_walls, gems)

        # Wenn wir 2 Ticks auf derselben Stelle stehen -> Plan verwerfen und zwingend explorieren
        if len(self.pos_history) >= 2 and self.pos_history[-1] == self.pos_history[-2]:
            if walls:
                self.bekannte_waende.intersection_update(walls)
            self.reset_plan()
            force = self.explore_move(bot_pos, set(walls))
            if force != 'WAIT':
                dx, dy = self.DIR_MAP[force]
                self.erwartete_pos = (bot_pos[0] + dx, bot_pos[1] + dy)
                return force, ziel, gem, reisezeit, 0

        if not self.plan:
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

        # 0) aktives Explorationsziel weiterverfolgen, falls erreichbar
        if self.aktuelles_explore_ziel:
            pfad = self.bfs(bot_pos, self.aktuelles_explore_ziel, alle_walls)
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
            ziel_liste = list(self.frontier_felder)
            self.rng.shuffle(ziel_liste)
            for ziel in ziel_liste:
                if ziel in self.recent_explore_targets:
                    continue
                pfad = self.bfs(bot_pos, ziel, alle_walls)
                if not pfad or len(pfad) < 2:
                    continue
                dist = len(pfad) - 1
                unbekannte = self.zaehle_unbekannte_nachbarn(ziel)
                odw = self.visit_count.get(ziel, 0)
                jitter = self.rng.random() * 0.5
                wertung = (dist + odw * 2 + jitter, -unbekannte, odw, ziel, pfad)
                kandidaten_frontier.append(wertung)

        kandidaten_unvisited = []
        if self.unbesuchte_felder and not self.full_map_sicht:
            ziel_unv = list(self.unbesuchte_felder)
            self.rng.shuffle(ziel_unv)
            for ziel in ziel_unv:
                if ziel in self.recent_explore_targets:
                    continue
                pfad = self.bfs(bot_pos, ziel, alle_walls)
                if not pfad or len(pfad) < 2:
                    continue
                dist = len(pfad) - 1
                odw = self.visit_count.get(ziel, 0)
                jitter = self.rng.random() * 0.5
                wertung = (dist + odw * 2 + jitter, odw, ziel, pfad)
                kandidaten_unvisited.append(wertung)

        ziel_pfadrichtung = None
        if kandidaten_frontier:
            kandidaten_frontier.sort()
            _, _, _, ziel, pfad = kandidaten_frontier[0]
            ziel_pfadrichtung = (ziel, pfad)
        elif kandidaten_unvisited:
            kandidaten_unvisited.sort()
            _, _, ziel, pfad = kandidaten_unvisited[0]
            ziel_pfadrichtung = (ziel, pfad)

        if ziel_pfadrichtung:
            ziel, pfad = ziel_pfadrichtung
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
            unseen = [
                (x, y)
                for x in range(self.width)
                for y in range(self.height)
                if (x, y) not in self.bekannter_boden
                and (x, y) not in alle_walls
                and (x, y) not in self.recent_explore_targets
            ]
            if unseen:
                self.rng.shuffle(unseen)
                kandidaten_unseen = []
                for ziel in unseen[:200]:  # begrenze Aufwand
                    pfad = self.bfs(bot_pos, ziel, alle_walls)  # allow_unknown=True
                    if not pfad or len(pfad) < 2:
                        continue
                    dist = len(pfad) - 1
                    kandidaten_unseen.append((dist, ziel, pfad))
                if kandidaten_unseen:
                    kandidaten_unseen.sort()
                    _, ziel, pfad = kandidaten_unseen[0]
                    self.aktuelles_explore_ziel = ziel
                    self.recent_explore_targets.append(ziel)
                    naechster = pfad[1]
                    delta = (naechster[0] - bot_pos[0], naechster[1] - bot_pos[1])
                    richtung = self.DELTA_TO_DIR.get(delta)
                    if richtung:
                        self.erwartete_pos = naechster
                        return richtung

        if self.full_map_sicht and not self.bekannte_gems:
            if self.center and tuple(bot_pos) != self.center:
                pfad_c = None
                if not self.hat_wand_gesehen and not alle_walls:
                    pfad_c = self.manhattan_path(bot_pos, self.center)
                if pfad_c is None:
                    pfad_c = self.bfs(bot_pos, self.center, alle_walls)
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
                pfad = self.bfs(bot_pos, ziel, alle_walls)
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
                pfad = self.bfs(bot_pos, ziel, alle_walls, allow_unknown=False)
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
