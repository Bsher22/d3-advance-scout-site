#!/usr/bin/env python3
"""Manage coach accounts for the online scouting site.

    python scouting/deploy/users.py add jsmith "John Smith"          new account, prints a temporary password
    python scouting/deploy/users.py add bsher "Brian" --role admin
    python scouting/deploy/users.py add jsmith "John Smith" --team "Rochester Tech"     account tied to a school
    python scouting/deploy/users.py team jsmith "Rochester Tech"     set or change the school on an account
    python scouting/deploy/users.py team jsmith none                 clear it
    python scouting/deploy/users.py reset jsmith                     new temporary password
    python scouting/deploy/users.py add jsmith "John Smith" --password "..."     use a password you choose (10+ characters)
    python scouting/deploy/users.py disable jsmith                   blocks sign-in, keeps the account
    python scouting/deploy/users.py enable jsmith
    python scouting/deploy/users.py remove jsmith
    python scouting/deploy/users.py list

A coach signs in with the temporary password and must choose his own before he sees anything.
Passwords are never stored: only a salted PBKDF2-SHA256 hash goes to Cloudflare.
Changes take effect within about a minute and need no redeploy.

Add --local to work against the local test store used by `npx wrangler pages dev`.
"""
import argparse, datetime, hashlib, json, os, re, secrets, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ITER = 100000            # the most Cloudflare Workers allows for PBKDF2
BINDING = "SCOUT_USERS"
WORDS = "amber birch cedar delta ember flint grove harbor inlet jasper kestrel linden maple north ochre prairie quartz ridge " \
        "sable timber umber valley willow yarrow zephyr anchor basin copper drift eagle fathom granite heron island juniper".split()


def temp_password():
    return "-".join(secrets.choice(WORDS) for _ in range(3)) + "-" + str(secrets.randbelow(90) + 10)


def make_hash(password, salt_hex=None):
    salt_hex = salt_hex or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), ITER, dklen=32).hex()
    return salt_hex, h


def wrangler(args, local, capture=False):
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        sys.exit("npx was not found. Install Node.js (https://nodejs.org), then run this again.")
    cmd = [npx, "wrangler", "kv"] + args + ["--binding", BINDING, "--local" if local else "--remote"]
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit("wrangler failed:\n" + (r.stderr or r.stdout).strip()[-1500:])
    return r.stdout if capture else None


def get(username, local):
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    r = subprocess.run([npx, "wrangler", "kv", "key", "get", "user:" + username, "--binding", BINDING,
                        "--local" if local else "--remote"], cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "").strip()
    try:
        return json.loads(out[out.index("{"):out.rindex("}") + 1])
    except Exception:
        return None


def clear_lock(username, local):
    """Forget failed sign-in attempts, so a locked-out coach can use his new password straight away."""
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    subprocess.run([npx, "wrangler", "kv", "key", "delete", "fail:" + username, "--binding", BINDING,
                    "--local" if local else "--remote"], cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="replace")


def put(username, rec, local):
    fd, path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(rec, fh)
        wrangler(["key", "put", "user:" + username, "--path", path], local)
    finally:
        os.remove(path)


def find_team(text):
    """Folder and display name of a school, from its folder name or its name as the site shows it."""
    p = os.path.join(os.path.dirname(HERE), "data", "index.js")
    if not os.path.exists(p):
        sys.exit("scouting/data/index.js was not found, so the school cannot be checked. Build the scouting data first.")
    teams = re.findall(r'\{"f":"([^"]+)","n":"([^"]+)"', open(p, encoding="utf-8").read())
    want = text.strip().lower()
    hit = [t for t in teams if want in (t[0].lower(), t[1].lower())]
    if len(hit) == 1:
        return hit[0]
    near = [t for t in teams if want in t[0].lower() or want in t[1].lower()][:8]
    sys.exit('No school is named exactly "%s".%s' % (text, (" Did you mean: " + ", ".join('"%s"' % t[1] for t in near)) if near else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["add", "reset", "disable", "enable", "remove", "list", "team"])
    ap.add_argument("username", nargs="?")
    ap.add_argument("name", nargs="?")
    ap.add_argument("--role", default="coach", choices=["coach", "admin"])
    ap.add_argument("--team", help="the coach's own school, by name or folder (add only)")
    ap.add_argument("--password", help="set this password instead of a temporary one (add and reset); he is not asked to change it")
    ap.add_argument("--local", action="store_true")
    a = ap.parse_args()

    if a.action == "list":
        out = wrangler(["key", "list"], a.local, capture=True)
        keys = [k["name"] for k in json.loads(out[out.index("["):out.rindex("]") + 1]) if k["name"].startswith("user:")]
        if not keys:
            print("No accounts yet.")
        for k in sorted(keys):
            r = get(k[5:], a.local) or {}
            state = "disabled" if r.get("disabled") else "temporary password not yet changed" if r.get("must_change") else "active"
            print("%-18s %-26s %-6s %-22s %s" % (k[5:], r.get("name", ""), r.get("role", ""), r.get("team_name") or r.get("team") or "(no team)", state))
        return

    if not a.username:
        ap.error("a username is required")
    u = a.username.strip().lower()
    if not re.match(r"^[a-z0-9._-]{2,40}$", u):
        sys.exit("Usernames are 2-40 characters: lowercase letters, digits, dot, dash or underscore.")
    rec = get(u, a.local)

    if a.action == "add":
        if rec:
            sys.exit("%s already exists. Use reset to give him a new temporary password." % u)
        tm = find_team(a.team) if a.team else None
        if a.password and len(a.password) < 10:
            sys.exit("Use at least 10 characters for the password.")
        pw = a.password or temp_password()
        salt, h = make_hash(pw)
        new = {"name": a.name or u, "role": a.role, "salt": salt, "hash": h, "iter": ITER, "must_change": not a.password,
               "created": datetime.date.today().isoformat()}
        if tm:
            new["team"], new["team_name"] = tm
        put(u, new, a.local)
        if a.password:
            print("Created %s (%s) with the password you gave. He can change it at /account." % (u, a.name or u))
        else:
            print("Created %s (%s).\n  Username: %s\n  Temporary password: %s\nHe will be asked to choose his own on first sign-in." % (u, a.name or u, u, pw))
        print("  Team: %s" % (tm[1] if tm else "none set (python users.py team %s \"School name\")" % u))
        return
    if not rec:
        sys.exit("No account named %s." % u)
    if a.action == "team":
        if not a.name:
            sys.exit('Give the school, for example:  python users.py team %s "Rochester Tech"   (or none to clear it)' % u)
        if a.name.strip().lower() == "none":
            rec.pop("team", None); rec.pop("team_name", None)
            put(u, rec, a.local)
            print("%s no longer has a team." % u)
        else:
            rec["team"], rec["team_name"] = find_team(a.name)
            put(u, rec, a.local)
            print("%s is now tied to %s. He sees it the next time he opens the site." % (u, rec["team_name"]))
        return
    if a.action == "reset":
        if a.password and len(a.password) < 10:
            sys.exit("Use at least 10 characters for the password.")
        pw = a.password or temp_password()
        rec["salt"], rec["hash"] = make_hash(pw)
        rec["iter"], rec["must_change"] = ITER, not a.password
        put(u, rec, a.local)
        clear_lock(u, a.local)
        print("Password for %s set to the one you gave." % u if a.password else "New temporary password for %s: %s" % (u, pw))
    elif a.action in ("disable", "enable"):
        rec["disabled"] = a.action == "disable"
        put(u, rec, a.local)
        print("%s is now %s." % (u, "disabled" if rec["disabled"] else "enabled"))
    elif a.action == "remove":
        wrangler(["key", "delete", "user:" + u], a.local)
        print("Removed %s." % u)


if __name__ == "__main__":
    main()
