// Login for the scouting site. Every page and data file passes through here.
// Accounts live in the SCOUT_USERS key-value store as  user:<username> -> {name, salt, hash, iter, role, team, must_change, disabled}
// team is the folder name of the coach's own school; the Matchup page compares every opponent with it. Set with users.py.
// Sessions are a signed cookie; SESSION_SECRET signs it.

const COOKIE = "sc_session";
const SESSION_DAYS = 14;
const MAX_FAILS = 8;            // then the username is locked for LOCK_MINUTES
const LOCK_MINUTES = 15;
const enc = new TextEncoder();

const b64u = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64u = (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
const unhex = (s) => new Uint8Array((s.match(/../g) || []).map((h) => parseInt(h, 16)));
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function hmac(secret, data) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64u(await crypto.subtle.sign("HMAC", key, enc.encode(data)));
}
function same(a, b) {            // constant-time compare
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}
async function pbkdf2(password, saltHex, iter) {
  const key = await crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveBits"]);
  return hex(await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt: unhex(saltHex), iterations: iter }, key, 256));
}
async function makeSession(env, username) {
  const body = b64u(enc.encode(JSON.stringify({ u: username, exp: Date.now() + SESSION_DAYS * 864e5 })));
  return body + "." + (await hmac(env.SESSION_SECRET, body));
}
async function readSession(env, request) {
  const m = (request.headers.get("Cookie") || "").match(new RegExp("(?:^|;\\s*)" + COOKIE + "=([^;]+)"));
  if (!m) return null;
  const [body, sig] = m[1].split(".");
  if (!body || !sig || !same(sig, await hmac(env.SESSION_SECRET, body))) return null;
  try {
    const s = JSON.parse(new TextDecoder().decode(unb64u(body)));
    return s.exp > Date.now() ? s : null;
  } catch (e) { return null; }
}
const cookie = (value, maxAge) => `${COOKIE}=${value}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`;
const getUser = async (env, u) => { const t = await env.SCOUT_USERS.get("user:" + u); return t ? JSON.parse(t) : null; };

function page(title, inner, status = 200) {
  return new Response(`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)} · D3 Advance Scout</title><meta name="robots" content="noindex">
<style>body{margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;background:#f3f5f7;color:#14202b}
.top{background:#12263a;color:#fff;padding:14px 20px;font-weight:700}
.box{max-width:380px;margin:9vh auto 0;background:#fff;border:1px solid #dde3e8;border-radius:10px;padding:24px}
h1{font-size:20px;margin:0 0 14px}label{display:block;font-size:13px;font-weight:600;margin:12px 0 4px}
input{width:100%;box-sizing:border-box;font:inherit;padding:10px;border:1px solid #b9c4cd;border-radius:6px}
button{margin-top:18px;width:100%;font:inherit;font-weight:700;padding:11px;border:0;border-radius:6px;background:#12263a;color:#fff;cursor:pointer}
.err{background:#fbeeea;color:#8f2416;border-radius:6px;padding:9px 11px;font-size:14px;margin-bottom:6px}
.ok{background:#e8f1fa;color:#17466f;border-radius:6px;padding:9px 11px;font-size:14px;margin-bottom:6px}
p.s{font-size:13px;color:#5d6b78;margin:14px 0 0}a{color:#1c5d99}</style></head>
<body><div class="top">D3 Advance Scout</div><div class="box">${inner}</div></body></html>`,
    { status, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } });
}
const loginPage = (next, msg, status) => page("Sign in", `<h1>Sign in</h1>${msg ? `<div class="err" role="alert">${esc(msg)}</div>` : ""}
<form method="post" action="/login"><input type="hidden" name="next" value="${esc(next)}">
<label for="u">Username</label><input id="u" name="username" autocomplete="username" autocapitalize="none" required autofocus>
<label for="p">Password</label><input id="p" name="password" type="password" autocomplete="current-password" required>
<button type="submit">Sign in</button></form><p class="s">Accounts are set up by the team. Ask for one if you need access.</p>`, status);
const accountPage = (user, msg, good, forced) => page("Your account", `<h1>${forced ? "Choose your own password" : "Change password"}</h1>
${forced ? '<p class="s" style="margin:0 0 10px">You signed in with a temporary password. Set your own to continue.</p>' : ""}
${msg ? `<div class="${good ? "ok" : "err"}" role="alert">${esc(msg)}</div>` : ""}
<form method="post" action="/account"><label for="o">Current password</label><input id="o" name="old" type="password" autocomplete="current-password" required>
<label for="n">New password (at least 10 characters)</label><input id="n" name="new" type="password" autocomplete="new-password" minlength="10" required>
<label for="c">New password again</label><input id="c" name="again" type="password" autocomplete="new-password" minlength="10" required>
<button type="submit">Save password</button></form><p class="s">Signed in as ${esc(user.name || "")}${user.team ? " · team: " + esc(user.team_name || user.team) : ""}. ${forced ? "" : '<a href="/">Back to the reports</a> · '}<a href="/logout">Sign out</a></p>`);

const safeNext = (n) => (typeof n === "string" && n.startsWith("/") && !n.startsWith("//") ? n : "/");

export async function onRequest(context) {
  const { request, env, next } = context;
  const url = new URL(request.url);
  const path = url.pathname;
  if (!env.SESSION_SECRET || !env.SCOUT_USERS) return new Response("The site is not configured yet (SESSION_SECRET / SCOUT_USERS).", { status: 500 });

  if (path === "/logout") return new Response(null, { status: 302, headers: { Location: "/login", "Set-Cookie": cookie("", 0) } });

  if (path === "/login") {
    if (request.method !== "POST") return loginPage(safeNext(url.searchParams.get("next")), "");
    const form = await request.formData();
    const username = String(form.get("username") || "").trim().toLowerCase();
    const password = String(form.get("password") || "");
    const dest = safeNext(form.get("next"));
    if (!/^[a-z0-9._-]{2,40}$/.test(username) || !password) return loginPage(dest, "Check the username and password.", 400);
    const failKey = "fail:" + username;
    const fails = parseInt((await env.SCOUT_USERS.get(failKey)) || "0", 10);
    if (fails >= MAX_FAILS) return loginPage(dest, `Too many attempts. Try again in ${LOCK_MINUTES} minutes.`, 429);
    const user = await getUser(env, username);
    // always do the hashing work, so a wrong username takes as long as a wrong password
    const got = await pbkdf2(password, user ? user.salt : "00".repeat(16), user ? user.iter : 100000);
    if (!user || user.disabled || !same(got, user.hash)) {
      await env.SCOUT_USERS.put(failKey, String(fails + 1), { expirationTtl: LOCK_MINUTES * 60 });
      return loginPage(dest, "That username and password do not match.", 401);
    }
    if (fails) await env.SCOUT_USERS.delete(failKey);
    return new Response(null, { status: 302, headers: { Location: user.must_change ? "/account" : dest,
      "Set-Cookie": cookie(await makeSession(env, username), SESSION_DAYS * 86400) } });
  }

  const session = await readSession(env, request);
  const user = session ? await getUser(env, session.u) : null;
  if (!user || user.disabled) {
    const wantsPage = request.method === "GET" && (request.headers.get("Accept") || "").includes("text/html");
    if (wantsPage) return new Response(null, { status: 302, headers: { Location: "/login?next=" + encodeURIComponent(path + url.search) } });
    return new Response("Sign in required.", { status: 401, headers: { "Cache-Control": "no-store" } });
  }

  if (path === "/account") {
    if (request.method !== "POST") return accountPage(user, "", false, !!user.must_change);
    const form = await request.formData();
    const oldp = String(form.get("old") || ""), newp = String(form.get("new") || ""), again = String(form.get("again") || "");
    if (!same(await pbkdf2(oldp, user.salt, user.iter), user.hash)) return accountPage(user, "The current password is not right.", false, !!user.must_change);
    if (newp.length < 10) return accountPage(user, "Use at least 10 characters.", false, !!user.must_change);
    if (newp !== again) return accountPage(user, "The two new passwords do not match.", false, !!user.must_change);
    if (newp === oldp) return accountPage(user, "Choose a password different from the current one.", false, !!user.must_change);
    const salt = hex(crypto.getRandomValues(new Uint8Array(16)));
    const updated = { ...user, salt, iter: 100000, hash: await pbkdf2(newp, salt, 100000), must_change: false, changed: new Date().toISOString() };
    await env.SCOUT_USERS.put("user:" + session.u, JSON.stringify(updated));
    return accountPage(updated, "Password saved.", true, false);
  }
  if (user.must_change) return new Response(null, { status: 302, headers: { Location: "/account" } });

  if (path === "/api/me") return new Response(JSON.stringify({ username: session.u, name: user.name || session.u, role: user.role || "coach", team: user.team || "" }),
    { headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });

  // An admin may switch the school his own account is tied to from the Matchup page; coaches are set with users.py.
  if (path === "/api/me/team") {
    if (request.method !== "POST") return new Response("POST only.", { status: 405 });
    if ((user.role || "coach") !== "admin") return new Response("Only an admin account can change its team here.", { status: 403 });
    let team = "";
    try { team = String((await request.json()).team || "").trim().toLowerCase(); } catch (e) { return new Response("Bad request.", { status: 400 }); }
    if (team && !/^[a-z0-9][a-z0-9._-]{0,79}$/.test(team)) return new Response("Bad team.", { status: 400 });
    const updated = { ...user };
    delete updated.team_name;
    if (team) updated.team = team; else delete updated.team;
    await env.SCOUT_USERS.put("user:" + session.u, JSON.stringify(updated));
    return new Response(JSON.stringify({ team }), { headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
  }

  // Coach grades for a team's own players, shared by everyone signed in for that team:  grades:<team> -> {players:{key:{...}}, updated, by}
  if (path === "/api/grades") {
    const json = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
    const okTeam = (t) => /^[a-z0-9][a-z0-9._-]{0,79}$/.test(t) && ((user.role || "coach") === "admin" || user.team === t);
    if (request.method === "GET") {
      const team = String(url.searchParams.get("team") || "");
      if (!okTeam(team)) return json({ error: "Not your team." }, 403);
      const t = await env.SCOUT_USERS.get("grades:" + team);
      return json(t ? JSON.parse(t) : { players: {} });
    }
    if (request.method !== "POST") return json({ error: "GET or POST only." }, 405);
    const raw = await request.text();
    if (raw.length > 120000) return json({ error: "Too large." }, 413);
    let body;
    try { body = JSON.parse(raw); } catch (e) { return json({ error: "Bad request." }, 400); }
    const team = String(body.team || "");
    if (!okTeam(team)) return json({ error: "Not your team." }, 403);
    const players = {};
    const grade = (v) => { const n = Math.round(Number(v) * 2) / 2; return n >= 1 && n <= 5 ? n : undefined; };      // 1 to 5, 3 is average
    for (const [k, p] of Object.entries(body.players || {}).slice(0, 150)) {
      if (!/^[a-z0-9]{1,60}$/.test(k) || !p || typeof p !== "object") continue;
      const rec = { n: String(p.n || "").slice(0, 60) };
      for (const t of ["hit", "eye", "pow", "run"]) { const g = grade(p[t]); if (g) rec[t] = g; }
      if (p.b && /^[LRS]$/.test(p.b)) rec.b = p.b;
      if (p.pos) rec.pos = String(p.pos).toUpperCase().replace(/[^A-Z0-9, ]/g, "").slice(0, 40);
      if (p.add) rec.add = 1;
      if (rec.add || rec.hit || rec.eye || rec.pow || rec.run) players[k] = rec;
    }
    const out = { players, updated: new Date().toISOString(), by: session.u };
    await env.SCOUT_USERS.put("grades:" + team, JSON.stringify(out));
    return json(out);
  }

  const res = await next();
  const out = new Response(res.body, res);
  out.headers.set("Cache-Control", "private, max-age=300");      // signed-in content must not sit in shared caches
  out.headers.set("X-Robots-Tag", "noindex");
  return out;
}
