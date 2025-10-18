#!/usr/bin/env python3
import sys, json
from brain import Brain

first_tick = True

width = 0
height = 0

def log(*msg):
    print(*msg, file=sys.stderr, flush=True)

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
        first_tick = False
        log(f"[init] seed={bot_seed} | arena={width}x{height}")
        brain.update_config(width, height, bot_seed, config)

    bot_pos = tuple(data.get("bot", [0, 0]))
    walls = set(map(tuple, data.get("wall", [])))
    floors = set(map(tuple, data.get("floor", [])))
    tick = data.get("tick", -1)
    brain.mark_visited(bot_pos)

    gems =data.get("visible_gems", [])
    action ,ziel ,bester_gem ,reisezeit ,rest =brain.next_move(bot_pos, walls, floors, gems)

    if action =='WAIT' and ziel is None:
        action = brain.explore_move(bot_pos, walls)
        log(f"[t{tick}] kein Ziel -> explore={action} | pos={bot_pos} | sicht={len(gems)}")
        print(action, flush=True)
        continue

    ttl = bester_gem.get("ttl") if bester_gem else None
    log(f"[t{tick}] sicht={len(gems)} ziel={ziel} ttl_an={ttl} reise={reisezeit} rest={rest} | action={action} | pos={bot_pos}")
    print(action, flush=True)
    
