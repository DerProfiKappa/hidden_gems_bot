#!/usr/bin/env python3
import sys, json, random

random.seed(1)
first_tick = True

for line in sys.stdin:
    data = json.loads(line)
    if first_tick:
        config = data.get("config", {})
        width = config.get("width")
        height = config.get("height")
        print(f"Random walker (Python) launching on a {width}x{height} map",
              file=sys.stderr, flush=True)
    move = random.choice(["N", "S", "E", "W"])
    print(move, flush=True)
    first_tick = False
