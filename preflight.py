#!/usr/bin/env python3
"""Check that the scouting site is ready to publish to Cloudflare Pages.

    python scouting/deploy/preflight.py            checks on this computer only
    python scouting/deploy/preflight.py --online   also asks Cloudflare: signed in, project, secret, accounts

Prints PASS / WARN / FAIL for each item. Exits 1 if anything is a FAIL (publish.bat stops there).
"""
import argparse, glob, json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SC = os.path.dirname(HERE)                      # scouting/
DATA = os.path.join(SC, "data")
PROJECT = "d3-advance-scout-site"
fails = warns = 0


def say(level, what, detail=""):
    global fails, warns
    fails += level == "FAIL"
    warns += level == "WARN"
    print("  %-4s  %s%s" % (level, what, ("  -  " + detail) if detail else ""))


def run(cmd, timeout=90):
    try:
        p = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, shell=(os.name == "nt"))
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:                       # not installed, timed out
        return 1, str(e)


def check_data():
    print("Data")
    idx = os.path.join(DATA, "index.js")
    if not os.path.exists(idx):
        return say("FAIL", "No scouting data", "run  python scouting/build_scouting_data.py")
    files = glob.glob(os.path.join(DATA, "t", "*.js"))
    size = sum(os.path.getsize(f) for f in files) + os.path.getsize(idx)
    big = max([os.path.getsize(f) for f in files] + [os.path.getsize(idx)])
    say("PASS" if files else "FAIL", "%d team files, %.0f MB" % (len(files), size / 1e6))
    say("PASS" if len(files) < 19000 else "FAIL", "Under Cloudflare's 20,000-file limit")
    say("PASS" if big < 24e6 else "FAIL", "Largest file %.1f MB (limit 25 MB)" % (big / 1e6))
    try:
        txt = open(idx, encoding="utf-8").read()
        d = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
        yrs = sorted(d.get("seasons") or [])
        say("PASS", "Index: %d teams, seasons %s, built %s" % (len(d["teams"]), "-".join(str(y) for y in (yrs[:1] + yrs[-1:])), d.get("built")))
        missing = [t["f"] + "_" + y for t in d["teams"] for y in t["s"] if not os.path.exists(os.path.join(DATA, "t", "%s_%s.js" % (t["f"], y)))]
        say("FAIL" if missing else "PASS", "Every team-season in the index has its file", ", ".join(missing[:5]))
    except Exception as e:
        say("FAIL", "index.js could not be read", str(e))
    # every school built by the current builder
    try:
        ver = int(re.search(r"^VER\s*=\s*(\d+)", open(os.path.join(SC, "build_scouting_data.py"), encoding="utf-8").read(), re.M).group(1))
        old = []
        for f in glob.glob(os.path.join(DATA, "_cache", "*.json")):
            try:
                if json.load(open(f, encoding="utf-8")).get("ver") != ver:
                    old.append(os.path.basename(f)[:-5])
            except Exception:
                old.append(os.path.basename(f)[:-5])
        say("WARN" if old else "PASS", "All schools built with the current builder (version %d)" % ver,
            ("%d are older, e.g. %s  -  run  python scouting/build_scouting_data.py" % (len(old), ", ".join(sorted(old)[:4]))) if old else "")
    except Exception as e:
        say("WARN", "Could not check builder version", str(e))


def check_page():
    print("Page")
    p = os.path.join(SC, "index.html")
    if not os.path.exists(p):
        return say("FAIL", "scouting/index.html is missing")
    s = open(p, encoding="utf-8").read()
    need = ["function vBrief", "function vUse", "function vPlayer", "function vRoster", "function vGame", "function whoAmI"]
    miss = [n.split()[1] for n in need if n not in s]
    say("FAIL" if miss else "PASS", "index.html has every view", "missing " + ", ".join(miss) if miss else "%d KB" % (len(s) // 1024))
    say("PASS" if 'name="viewport"' in s else "WARN", "Sized for phones and tablets")
    say("PASS" if os.path.exists(os.path.join(SC, "sw.js")) else "WARN", "Offline support present (sw.js)")
    mw = os.path.join(HERE, "functions", "_middleware.js")
    say("PASS" if os.path.exists(mw) else "FAIL", "Login code present (functions/_middleware.js)")


def check_config():
    print("Cloudflare settings on this computer")
    wt = os.path.join(HERE, "wrangler.toml")
    t = open(wt, encoding="utf-8").read() if os.path.exists(wt) else ""
    m = re.search(r'binding\s*=\s*"SCOUT_USERS"\s*\n\s*id\s*=\s*"([^"]*)"', t)
    ok = bool(m) and re.fullmatch(r"[0-9a-f]{32}", m.group(1) or "") is not None
    say("PASS" if ok else "FAIL", "Account store id is in wrangler.toml", "" if ok else "do SETUP.md step 2 and paste the id")
    say("PASS" if shutil.which("node") else "FAIL", "Node.js is installed", "" if shutil.which("node") else "install it from nodejs.org")
    wr = os.path.exists(os.path.join(HERE, "node_modules", "wrangler"))
    say("PASS" if wr else "WARN", "Cloudflare tool installed here", "" if wr else "run  npm install  in scouting\\deploy")
    site = os.path.join(HERE, "site")
    if os.path.isdir(site):
        bad = [n for n in ("_cache", "_aux", ".dev.vars", ".env") if os.path.exists(os.path.join(site, n)) or os.path.exists(os.path.join(site, "data", n))]
        say("FAIL" if bad else "PASS", "Nothing private in the upload folder", ", ".join(bad))
    return ok


def check_online(kv_ok):
    print("Cloudflare account")
    rc, out = run(["npx", "wrangler", "whoami"])
    signed = rc == 0 and "not authenticated" not in out.lower()
    say("PASS" if signed else "FAIL", "Signed in to Cloudflare", "" if signed else "run  npx wrangler login")
    if not signed:
        return
    rc, out = run(["npx", "wrangler", "pages", "project", "list"])
    has = PROJECT in out
    say("PASS" if has else "FAIL", "Pages project %s exists" % PROJECT, "" if has else "do SETUP.md step 3")
    if has:
        rc, out = run(["npx", "wrangler", "pages", "secret", "list", "--project-name", PROJECT])
        ok = "SESSION_SECRET" in out
        say("PASS" if ok else "FAIL", "SESSION_SECRET is set", "" if ok else "do SETUP.md step 4")
    if kv_ok:
        rc, out = run([sys.executable, os.path.join(HERE, "users.py"), "list"])
        n = len(re.findall(r"(?m)^\s*\S+\s+.*\b(admin|coach)\b", out))
        say("PASS" if rc == 0 and n else "WARN", "Coach accounts: %d" % n, "" if n else "add one with  python users.py add <username> \"Name\"  (after the first publish is fine)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--online", action="store_true", help="also check the Cloudflare account (needs  npx wrangler login)")
    a = ap.parse_args()
    check_data()
    check_page()
    kv_ok = check_config()
    if a.online:
        check_online(kv_ok)
    print()
    if fails:
        print("NOT READY: %d item(s) must be fixed%s." % (fails, (", %d warning(s)" % warns) if warns else ""))
        sys.exit(1)
    print("READY to publish%s." % ((" (%d warning(s) to look at)" % warns) if warns else ""))


if __name__ == "__main__":
    main()
