# Deploying the TTB Label Verifier

This guide walks through publishing the prototype to a public URL on **Vercel**
and on **Replit**. Both paths work with the config files already committed to
this repo (`vercel.json` + `api/index.py` for Vercel; `.replit` for Replit).

**Before you start, decide on a mode:**

- **Demo mode** (`LABEL_DEMO=1`) — runs immediately, no API key, but only
  recognizes the four bundled sample labels. Good for a first deploy / smoke
  test of the URL.
- **Live mode** — set `ANTHROPIC_API_KEY` and it reads any uploaded label.

You can deploy in demo mode first to confirm the URL works, then add the key
and redeploy.

---

## Option A — Vercel

Vercel runs the FastAPI app as a Python serverless function. `api/index.py`
exposes the ASGI app and `vercel.json` rewrites every route to it.

### A1. Push the repo to GitHub (recommended path)

```bash
# from the project root
gh repo create ttb-label-verifier --public --source=. --push
# …or create a repo in the GitHub UI and:
#   git remote add origin https://github.com/<you>/ttb-label-verifier.git
#   git push -u origin main
```

### A2. Import the project into Vercel

1. Go to <https://vercel.com/new> and sign in (GitHub login is easiest).
2. Click **Import** next to your `ttb-label-verifier` repository.
3. On the configuration screen, leave everything at its defaults:
   - **Framework Preset:** Other (Vercel auto-detects the Python function).
   - **Build/Output settings:** none needed — `vercel.json` handles routing
     and `requirements.txt` drives the install.
4. Expand **Environment Variables** and add the mode you chose:
   - Demo: name `LABEL_DEMO`, value `1`.
   - Live: name `ANTHROPIC_API_KEY`, value `sk-ant-…`
     (optionally `LABEL_MODEL` = `claude-haiku-4-5`).
5. Click **Deploy**. The first build takes ~1–2 minutes.
6. When it finishes, click **Visit** — your URL is
   `https://ttb-label-verifier.vercel.app` (or similar).

### A3. (Alternative) Deploy from the CLI, no GitHub

```bash
npm i -g vercel
vercel login
vercel            # answer the prompts; accept defaults
vercel env add LABEL_DEMO production         # type: 1
# or, for live mode:
vercel env add ANTHROPIC_API_KEY production  # paste your key
vercel --prod     # promote to the production URL
```

### A4. Verify

Open the URL, confirm the badge in the header reads **Demo mode** (or
**Live**), then on the *Check One Label* tab upload `samples/old_tom_bourbon.png`
with the matching application fields and confirm a green **PASS**.

### Vercel notes & gotchas

- **Serverless timeout.** The Hobby plan caps a function at 10 s, Pro at 60 s.
  A single label easily finishes inside 10 s. For large **batches** (100+
  labels in one request) on Hobby you may hit the cap — split the batch, or
  add `"functions": { "api/index.py": { "maxDuration": 60 } }` to `vercel.json`
  on a Pro plan.
- **Stateless.** Vercel functions don't keep disk or memory between requests —
  fine here, since the app stores nothing.
- **Secrets.** Never commit your API key. It lives only in Vercel's
  Environment Variables. After changing an env var, redeploy (Vercel →
  Deployments → ⋯ → Redeploy) for it to take effect.

---

## Option B — Replit

Replit can both run the app in its workspace and publish it as an
always-on **Deployment** with a public URL. The committed `.replit` file sets
the run command, port mapping, and an autoscale deployment target.

### B1. Create the Repl

Either:

- **From GitHub:** Replit → **Create** → **Import from GitHub** → paste your
  repo URL. _(Push to GitHub first; see step A1.)_
- **Without GitHub:** Replit → **Create** → **Python** template → then drag the
  project files into the file tree (or use the Shell + `git clone`). The
  committed `.replit` will be picked up automatically.

### B2. Install dependencies

Open the **Shell** tab and run:

```bash
pip install -r requirements.txt
```

(Replit's Python 3.12 module includes `pip`. This is a one-time step; it
persists with the Repl.)

### B3. Run it in the workspace

Click the green **Run** button. The `.replit` file runs `python -m app.main`,
which starts uvicorn on port 8000; Replit maps that to an HTTPS preview pane
and a `*.replit.dev` URL. You should see the app load with a **Demo mode**
badge (demo mode is preset in `.replit`).

### B4. Switch to live mode (optional)

1. Open the **Secrets** tool (lock icon) in the left sidebar.
2. Add a secret: key `ANTHROPIC_API_KEY`, value `sk-ant-…`.
3. In `.replit`, remove the `LABEL_DEMO = "1"` line under `[env]` **and** the
   `LABEL_DEMO` reference in the deployment comment (so live mode is used).
4. Stop and **Run** again.

### B5. Publish a public, always-on URL

1. Click **Deploy** (top-right) → choose **Autoscale** (cheapest for bursty,
   request-driven traffic like this).
2. Replit reads the `[deployment]` block from `.replit`
   (`run = ["python", "-m", "app.main"]`); the app listens on the `$PORT`
   Replit injects — no change needed.
3. Under the deployment's **Secrets/Environment**, add `ANTHROPIC_API_KEY`
   for live mode (workspace Secrets are separate from deployment Secrets).
4. Click **Deploy**. When it finishes you get a stable
   `https://<name>.replit.app` URL.

### B6. Verify

Open the deployment URL and run the same check as A4
(`samples/old_tom_bourbon.png` → green **PASS**).

### Replit notes & gotchas

- **Workspace URL vs. Deployment URL.** The `*.replit.dev` preview only stays
  up while the workspace is open. Use a **Deployment** (`*.replit.app`) for a
  URL you can hand to reviewers.
- **Two separate secret stores.** A key added to workspace **Secrets** does
  *not* automatically apply to a **Deployment** — set it in both places if you
  want live mode in each.
- **Autoscale vs. Reserved VM.** Autoscale scales to zero when idle (cheapest,
  slight cold-start delay). If you need it instantly responsive at all times,
  choose **Reserved VM** instead — same run command.

---

## Which should I use?

| | Vercel | Replit |
|---|---|---|
| Best for | A polished, shareable demo URL | Editing + running in one place |
| Setup speed | ~2 min (after GitHub push) | ~2 min (in-browser, no Git required) |
| Long batches (100+ labels/request) | Watch the function timeout | No hard request cap on a Reserved VM |
| Cost | Free Hobby tier | Free to develop; deployments are paid/credit-based |

For a quick link to send the TTB team, **Vercel** is the smoothest. For an
environment where a reviewer can also poke at the code, **Replit** is handier.

Either way, the only outbound dependency in live mode is `api.anthropic.com` —
keep Marcus's firewall note in mind for any eventual on-premise TTB deployment.
