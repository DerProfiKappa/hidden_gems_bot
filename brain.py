from collections import deque


def strecke(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class Brain:
    def __init__(self):
        self.width = 0
        self.height = 0
        self.besuchte_felder = set()
        self.hat_wand_gesehen = False
        self.bekannte_gems ={}
        self.center =None
        self.RICHTUNG = [
            ('N', (0, -1)),
            ('E', (1, 0)),
            ('S', (0, 1)),
            ('W', (-1, 0))
        ]
        self.DIR_MAP = dict(self.RICHTUNG)
        self.DELTA_TO_DIR = {delta: name for name, delta in self.RICHTUNG}
        self.plan =[]          # plan
        self.geplantes_ziel=None
        self.geplanter_gem =None
        self.erwartete_pos = None
        self.geplante_reisezeit =None
        self.bekannte_waende = set()
        self.bekannter_boden = set()
        self.unbesuchte_felder = set()

    def update_config(self, width, height, seed):
        self.width =width
        self.height =height
        if width>0 and height >0:
            x =max(1, min(width-2,width//2))
            y =max(1,min(height-2, height//2))
            self.center =(x, y)

    def im_feld(self, x, y):
        if self.width <= 0 or self.height <= 0:
            return True
        return 0 <= x < self.width and 0 <= y < self.height

    def mark_visited(self, pos):
        punkt =tuple(pos)
        self.besuchte_felder.add(punkt)
        self.unbesuchte_felder.discard(punkt)

    def aktualisiere_umgebung(self, bot_pos, walls, floors):
        if walls:
            self.bekannte_waende.update(set(walls))
            self.hat_wand_gesehen = True
        sichtbarer_boden = set(floors)
        if sichtbarer_boden:
            self.bekannter_boden.update(sichtbarer_boden)
            for feld in sichtbarer_boden:
                if feld not in self.besuchte_felder and feld not in self.bekannte_waende:
                    self.unbesuchte_felder.add(feld)
        self.unbesuchte_felder.discard(tuple(bot_pos))

    def kombi_walls(self, walls):
        mix = set(walls)
        if self.bekannte_waende:
            mix.update(self.bekannte_waende)
        return mix

    def reset_plan(self):
        self.plan =[]          # reset
        self.geplantes_ziel=None
        self.geplanter_gem =None
        self.erwartete_pos = None
        self.geplante_reisezeit =None

    def aktualisiere_gems(self, bot_pos, sichtbare_gems):
        bot_pos =tuple(bot_pos)
        neue_cache ={}

        for pos, ttl in self.bekannte_gems.items():
            rest =ttl-1
            if rest>0 and pos !=bot_pos:
                neue_cache[pos] =rest

        for gem in sichtbare_gems:
            position =tuple(gem.get("position" ,[]))
            ttl_roh =gem.get("ttl")
            if position and ttl_roh is not None:
                try:
                    ttl =int(ttl_roh)
                except (TypeError ,ValueError):
                    continue
                neue_cache[position] = ttl

        self.bekannte_gems = neue_cache

    def manhattan_path(self, start, ziel):
        pfad =[tuple(start)]
        x, y =start
        zx ,zy =ziel

        if x !=zx:
            schritt_x = 1 if zx>x else -1
            while x!= zx:
                x +=schritt_x
                if not self.im_feld(x ,y):
                    return None
                pfad.append((x ,y))

        if y!= zy:
            schritt_y = 1 if zy>y else -1
            while y != zy:
                y += schritt_y
                if not self.im_feld(x ,y):
                    return None
                pfad.append((x ,y))

        return pfad

    def bfs(self, start, ziel, walls):
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

        beste_wahl =None

        for position ,ttl in self.bekannte_gems.items():
            if ttl <= 0:
                continue
            pfad =None
            if not self.hat_wand_gesehen and not walls :
                pfad = self.manhattan_path(bot_pos, position)
            if pfad is None:
                pfad =self.bfs(bot_pos ,position, walls)
            if not pfad:
                continue

            reisezeit = len(pfad)-1
            arrival_ttl = ttl - reisezeit
            if arrival_ttl <= 0:
                continue

            zeit = max(1 ,reisezeit)
            effizienz = arrival_ttl / zeit

            wertung =(-effizienz , -arrival_ttl ,reisezeit ,position)
            if beste_wahl is None or wertung <beste_wahl[0]:
                bestes_gem ={"position": list(position) , "ttl": arrival_ttl}
                beste_wahl =(wertung ,bestes_gem ,pfad ,reisezeit)

        if beste_wahl is None:
            return None, None, None, None

        _, bestes_gem, pfad, reisezeit = beste_wahl
        return tuple(bestes_gem["position"]), bestes_gem, pfad, reisezeit

    def idle_move(self, bot_pos, walls):
        if not self.center:
            return 'WAIT'

        cx ,cy =self.center
        bx ,by =bot_pos
        kandidaten =[]

        if bx < cx:
            kandidaten.append('E')
        elif bx >cx:
            kandidaten.append('W')

        if by <cy:
            kandidaten.append('S')
        elif by > cy:
            kandidaten.append('N')

        if not kandidaten:
            return 'WAIT'

        for name in kandidaten:
            dx ,dy =self.DIR_MAP[name]
            nx =bx+dx
            ny =by+dy
            if self.im_feld(nx ,ny) and (nx, ny) not in walls:
                return name

        return 'WAIT'

    def stelle_plan_sicher(self, bot_pos, walls, gems):
        self.reset_plan()

        if not self.bekannte_gems:
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
        self.aktualisiere_umgebung(bot_pos, walls, floors)
        alle_walls = self.kombi_walls(walls)
        self.aktualisiere_gems(bot_pos, gems)

        ziel, gem, reisezeit = self.stelle_plan_sicher(bot_pos, alle_walls, gems)

        if not self.plan:
            idle = self.idle_move(bot_pos, alle_walls)
            if idle != 'WAIT':
                dx, dy = self.DIR_MAP[idle]
                self.erwartete_pos = (bot_pos[0]+dx , bot_pos[1]+dy)
            else:
                self.erwartete_pos = tuple(bot_pos)
            return idle ,ziel ,gem ,reisezeit ,0

        if self.plan and self.plan[0][1] in alle_walls:
            ziel, gem, reisezeit = self.stelle_plan_sicher(bot_pos, alle_walls, gems)
            if not self.plan or (self.plan and self.plan[0][1] in alle_walls):
                ausweich = self.explore_move(bot_pos, alle_walls)
                return ausweich ,ziel ,gem ,reisezeit ,0

        richtung, naechster = self.plan.pop(0)
        self.erwartete_pos = naechster
        rest = len(self.plan)    # rest schritte 
        return richtung, ziel, gem, reisezeit, rest

    def explore_move(self, bot_pos, walls):
        alle_walls = self.kombi_walls(walls)
        if self.unbesuchte_felder:
            ziel = min(self.unbesuchte_felder, key=lambda pos: strecke(bot_pos, pos))
            pfad = self.bfs(bot_pos, ziel, alle_walls)
            if pfad and len(pfad)>1:
                naechster = pfad[1]
                delta = (naechster[0]-bot_pos[0], naechster[1]-bot_pos[1])
                richtung = self.DELTA_TO_DIR.get(delta)
                if richtung:
                    self.erwartete_pos = naechster
                    return richtung
            self.unbesuchte_felder.discard(ziel)
        x, y = bot_pos
        gerade_zeile = (y % 2 == 0)

        # feste Bewegungsreihenfolge
        prioritaet = []
        if gerade_zeile:
            prioritaet.append('E')  # gerade Zeilen-> nach rechts
        else:
            prioritaet.append('W')  # ungerade zeilen->nach links

        prioritaet.append('S')  #unten
        prioritaet.append('N')  #oben
        prioritaet.append('W' if gerade_zeile else 'E')  #letzte Option==> zurück

        for name in prioritaet:
            dx, dy = self.DIR_MAP[name]
            nx = x + dx
            ny = y + dy
            if self.im_feld(nx, ny) and (nx, ny) not in alle_walls:
                self.unbesuchte_felder.discard((nx, ny))
                self.erwartete_pos = (nx, ny)
                return name

        # Wenn alles blockiert ist ---> stehen bleiben
        self.erwartete_pos = tuple(bot_pos)
        return 'WAIT'
