# Putting the scouting site online with coach logins

The site is hosted on Cloudflare Pages. Every page and data file sits behind a sign-in; each coach has his own
username and password. Nothing here touches the Railway database.

## One-time setup (about 15 minutes)

Run these in a terminal from `scouting\deploy`. You need Node.js (you already have it for `frontend`).

1. **Install the Cloudflare tool and sign in.** A browser window opens for your Cloudflare account.

       npm install
       npx wrangler login

2. **Create the store that holds the accounts.** It prints an `id`.

       npx wrangler kv namespace create SCOUT_USERS

   Open `wrangler.toml` and replace `PASTE_NAMESPACE_ID_HERE` with that id.

3. **Create a private repository on GitHub** named `d3-advance-scout-site`. Leave it empty (no README). It must
   be private: it holds the data the login protects. Then send this folder to it:

       connect_github.bat https://github.com/YOUR-NAME/d3-advance-scout-site.git

4. **Create the site from that repository.** In the Cloudflare dashboard: Workers & Pages > Create > Pages >
   connect to Git, and choose `d3-advance-scout-site`. Project name `d3-advance-scout-site`, production branch `main`,
   no framework, build command empty, build output directory `site`. Save and deploy.

5. **Set the secret that signs the login sessions**, then deploy once more so it takes effect (Deployments >
   Retry deployment). Keep no copy; if it is ever replaced, everyone simply signs in again.

       python -c "import secrets; print(secrets.token_urlsafe(48))"
       npx wrangler pages secret put SESSION_SECRET --project-name d3-advance-scout-site

   The address is `https://d3-advance-scout-site.pages.dev` (a longer one if that name is taken).

6. **Create your own account, then the coaches'.**

       python users.py add bsher "Brian" --role admin
       python users.py add jsmith "John Smith"

   Each prints a temporary password. Give the coach his username, that password and the address. He must choose
   his own password the first time he signs in.

## Check before publishing

    python preflight.py            data, page and settings on this computer
    python preflight.py --online   also checks the Cloudflare sign-in, project, secret and accounts

`publish.bat` runs the first one itself and stops if anything is marked FAIL.

## Day to day

| To do this | Run |
|---|---|
| Update the site after new games | `publish.bat` (builds, then pushes to GitHub; Cloudflare publishes it) |
| See who has an account | `python users.py list` |
| Coach forgot his password | `python users.py reset jsmith` |
| Coach leaves the staff | `python users.py remove jsmith` (or `disable`) |

Account changes take effect within about a minute. They do not need a publish.

## How the login works

- `functions/_middleware.js` runs in front of every request. Without a valid session it sends pages to `/login`
  and refuses data files.
- Passwords are stored only as salted PBKDF2-SHA256 hashes (100,000 rounds, the Cloudflare maximum).
- A session lasts 14 days and is a signed, HTTP-only, secure cookie.
- Eight wrong passwords lock that username for 15 minutes.
- Coaches change their password at `/account` and sign out at `/logout`.

## Limits

- No "forgot password" email: you reset it for him with `users.py reset`.
- No record of who viewed what.
- Disabling an account blocks new requests at once, but pages he already has open stay on his screen.
- To use your own address (say scout.yourdomain.com), add it under the Pages project's Custom domains in Cloudflare.

## Testing on this computer first (optional)

    echo SESSION_SECRET=anything-for-local-testing > .dev.vars
    python build_site.py
    python users.py add test "Test" --local
    npx wrangler pages dev site

Then open http://localhost:8788. Browsers treat localhost as secure, so the login cookie works there.
