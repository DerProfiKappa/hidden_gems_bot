def strecke(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class Brain:
    def __init__(self):
        self.width = 0
        self.height = 0
        self.besuchte_felder = set()
        self.gewicht_ttl = 0.6
        self.RICHTUNG = [
            ('N', (0, -1)),
            ('E', (1, 0)),
            ('S', (0, 1)),
            ('W', (-1, 0))
        ]
        self.DIR_MAP = dict(self.RICHTUNG)

    def update_config(self, width, height, seed):
        self.width = width
        self.height = height

    def im_feld(self, x, y):
        if self.width <= 0 or self.height <= 0:
            return True
        return 0 <= x < self.width and 0 <= y < self.height

    def mark_visited(self, pos):
        self.besuchte_felder.add(tuple(pos))

    def choose_target(self, bot_pos, gems):
        def bewertung(gem):
            position = tuple(gem["position"])
            entfernung = strecke(bot_pos, position)
            ttl = int(gem.get("ttl", 0))

            score = entfernung - self.gewicht_ttl * ttl   # kleiner Wert = besseres Ziel

            if entfernung > ttl:    # wenn wahrscheinlich zu spät erreichbar → abwerten
                score += 10
            return (score, entfernung, position)

        bestes_gem = min(gems, key=bewertung)
        return tuple(bestes_gem["position"]), bestes_gem

    def explore_move(self, bot_pos, walls):
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
            if self.im_feld(nx, ny) and (nx, ny) not in walls:
                return name

        # Wenn alles blockiert ist ---> stehen bleiben
        return 'WAIT'
