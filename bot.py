#!/usr/bin/env python3
import sys, json, random

rng = None

first_tick = True

for line in sys.stdin:
    data = json.loads(line)
    if first_tick:
        config = data.get("config", {})
        width = config.get("width")
        height = config.get("height")
        bot_seed = config.get("bot_seed", 1)
        rng = random.Random(bot_seed ^ 2008)
        print(f"Random walker (Python) launching on a {width}x{height} map",
              file=sys.stderr, flush=True)
        first_tick = False
    move = random.choice(["N", "S", "E", "W"])
    print(move, flush=True)