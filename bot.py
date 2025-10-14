#!/usr/bin/env python3
import sys, json, random
from brain import Brain

rng = None
first_tick = True

RICHTUNG = [('N', (0, -1)), ('E', (1, 0)), ('S', (0, 1)), ('W', (-1, 0))]

width = 0
height = 0

def log(*msg):
    print(*msg, file=sys.stderr, flush=True)

def im_feld(nx, ny):

    if width <= 0 or height <= 0:
        return True
    return 0 <= nx < width and 0 <= ny < height


def strecke(a, b):
    return abs(a[0]-b[0]) + abs(a[1]-b[1])

def step_towards(startp, ziel, walls):
    x, y = startp
    tx, ty = ziel

    if tx > x:
        dx = 1
    elif tx < x:
        dx = -1
    else:
        dx = 0

    if ty > y:
        dy = 1
    elif ty < y:
        dy = -1
    else:
        dy = 0

    kandidaten = []

    dist_x = abs(tx - x)
    dist_y = abs(ty - y)

    if dist_x >= dist_y:
        # zuerst horizontal, dann vertikal
        if dx != 0:
            if dx == 1:
                kandidaten.append(('E', (x + 1, y)))
            else:
                kandidaten.append(('W', (x - 1, y)))
        if dy != 0:
            if dy == 1:
                kandidaten.append(('S', (x, y + 1)))
            else:
                kandidaten.append(('N', (x, y - 1)))
    else:
        # zuerst vertikal, dann horizontal
        if dy != 0:
            if dy == 1:
                kandidaten.append(('S', (x, y + 1)))
            else:
                kandidaten.append(('N', (x, y - 1)))
        if dx != 0:
            if dx == 1:
                kandidaten.append(('E', (x + 1, y)))
            else:
                kandidaten.append(('W', (x - 1, y)))

    # -- > Wände blocken
    for move, (nx, ny) in kandidaten:
        if im_feld(nx, ny) and (nx, ny) not in walls:
            return move
    return 'WAIT'

brain = Brain()

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        print("WAIT", flush=True)
        continue

    if first_tick:
        config = data.get("config", {})
        bot_seed = config.get("bot_seed", 1)
        width  = config.get("width", 0)
        height = config.get("height", 0)
        rng = random.Random(bot_seed ^ 2008)  # deterministisch
        first_tick = False
        log(f"[init] seed={bot_seed} | arena={width}x{height}")
        brain.update_config(width, height, bot_seed)

    bot_pos = tuple(data.get("bot", [0, 0]))
    walls = set(map(tuple, data.get("wall", [])))
    tick = data.get("tick", -1)
    brain.mark_visited(bot_pos)

    gems = data.get("visible_gems", [])
    if not gems:
        move = brain.explore_move(bot_pos, walls)
        log(f"[t{tick}] keine Gems -> explore={move} | pos={bot_pos}")
        print(move, flush=True)
        continue

    target, bester_gem = brain.choose_target(bot_pos, gems)

    action = step_towards(bot_pos, target, walls)
    log(f"[t{tick}] target={target} ttl={bester_gem.get('ttl')} | action={action} | pos={bot_pos}")
    print(action, flush=True)