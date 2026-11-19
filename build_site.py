#!/usr/bin/env python3
"""Copy what the online site needs into scouting/deploy/site (the page and the team data, nothing else).

    python scouting/deploy/build_site.py

Leaves out the builder's working files (_cache, _aux), which hold nothing the page uses.
"""
import os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)                  # scouting/
OUT = os.path.join(HERE, "site")


def main():
    if not os.path.exists(os.path.join(SRC, "data", "index.js")):
        sys.exit("No scouting data found. Run  python scouting/build_scouting_data.py  first.")
    os.makedirs(os.path.join(OUT, "data", "t"), exist_ok=True)
    shutil.copy2(os.path.join(SRC, "index.html"), os.path.join(OUT, "index.html"))
    if os.path.exists(os.path.join(SRC, "sw.js")):          # keeps opened pages usable with no signal
        shutil.copy2(os.path.join(SRC, "sw.js"), os.path.join(OUT, "sw.js"))
    shutil.copy2(os.path.join(SRC, "data", "index.js"), os.path.join(OUT, "data", "index.js"))
    src_t = os.path.join(SRC, "data", "t")
    want = {f for f in os.listdir(src_t) if f.endswith(".js")}
    n = b = 0
    for f in sorted(want):
        s, d = os.path.join(src_t, f), os.path.join(OUT, "data", "t", f)
        if not os.path.exists(d) or os.path.getmtime(s) > os.path.getmtime(d) or os.path.getsize(s) != os.path.getsize(d):
            shutil.copy2(s, d)
            n += 1
        b += os.path.getsize(s)
    stale = [f for f in os.listdir(os.path.join(OUT, "data", "t")) if f not in want]
    for f in stale:                          # a team file that no longer exists upstream
        try:
            os.remove(os.path.join(OUT, "data", "t", f))
        except OSError:
            pass
    with open(os.path.join(OUT, "_headers"), "w", encoding="utf-8") as fh:
        fh.write("/*\n  X-Frame-Options: DENY\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: no-referrer\n"
                 "/sw.js\n  Cache-Control: no-cache\n")
    print("site ready: %d team files (%d copied this time), %.0f MB, in %s" % (len(want), n, b / 1e6, OUT))


if __name__ == "__main__":
    main()
