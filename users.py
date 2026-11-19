#!/usr/bin/env python3
"""Manage coach accounts for the online scouting site.

    python scouting/deploy/users.py add jsmith "John Smith"          new account, prints a temporary password
    python scouting/deploy/users.py add bsher "Brian" --role admin
    python scouting/deploy/users.py reset jsmith                     new temporary password
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["add", "reset", "disable", "enable", "remove", "list"])
    ap.add_argument("username", nargs="?")
    ap.add_argument("name", nargs="?")
    ap.add_argument("--role", default="coach", choices=["coach", "admin"])
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
            print("%-18s %-26s %-6s %s" % (k[5:], r.get("name", ""), r.get("role", ""), state))
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
        pw = temp_password()
        salt, h = make_hash(pw)
        put(u, {"name": a.name or u, "role": a.role, "salt": salt, "hash": h, "iter": ITER, "must_change": True,
                "created": datetime.date.today().isoformat()}, a.local)
        print("Created %s (%s).\n  Username: %s\n  Temporary password: %s\nHe will be asked to choose his own on first sign-in." % (u, a.name or u, u, pw))
        return
    if not rec:
        sys.exit("No account named %s." % u)
    if a.action == "reset":
        pw = temp_password()
        rec["salt"], rec["hash"] = make_hash(pw)
        rec["iter"], rec["must_change"] = ITER, True
        put(u, rec, a.local)
        clear_lock(u, a.local)
        print("New temporary password for %s: %s" % (u, pw))
    elif a.action in ("disable", "enable"):
        rec["disabled"] = a.action == "disable"
        put(u, rec, a.local)
        print("%s is now %s." % (u, "disabled" if rec["disabled"] else "enabled"))
    elif a.action == "remove":
        wrangler(["key", "delete", "user:" + u], a.local)
        print("Removed %s." % u)


if __name__ == "__main__":
    main()
