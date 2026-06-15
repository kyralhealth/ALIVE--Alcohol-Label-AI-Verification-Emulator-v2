# Alcohol Label AI-Verification Emulator (ALIVE)

AI-assisted verification of alcohol beverage label artwork against COLA
application data. An agent (or a batch of up to 300 labels) gets a
color-coded verdict in seconds: **PASS** / **NEEDS REVIEW** / **ISSUES FOUND**,
with per-field detail.

`label image → Claude (transcription only) → deterministic rule engine → verdict`

## Quick Start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Try it immediately with the bundled sample labels (no API key needed):
LABEL_DEMO=1 .venv/bin/uvicorn app.main:app --port 8000

# Real label reading:
export ANTHROPIC_API_KEY=sk-ant-...
.venv/bin/uvicorn app.main:app --port 8000
```

Open <http://localhost:8000>. In demo mode, upload any of the images in
`samples/` (single tab) or all four plus `samples/applications.csv`
(batch tab).

Run the tests:

```bash
.venv/bin/python -m pytest
```

Regenerate the sample labels:

```bash
.venv/bin/python scripts/generate_samples.py
```

## Checklist

| Check | How |
|---|---|
| Brand name | Tiered: exact → match; case/punctuation-only difference → match with a note (so `STONE'S THROW` vs `Stone's Throw` doesn't bounce); ≥85% similar → **needs review**; else mismatch |
| Class/type | Same tiered comparison |
| Alcohol content | Numeric parse of free text (`45% Alc./Vol. (90 Proof)`, `45`, `90 proof`…); also cross-checks that a printed proof equals 2× the ABV |
| Net contents | Unit-normalized (mL/cL/L/fl oz/gal), so `1 L` matches `1000 mL` |
| Government warning — text | Word-for-word against 27 CFR Part 16; any deviation is rejected with a word-level diff in the note |
| Government warning — capitalization | `GOVERNMENT WARNING:` must be in capital letters (title case is a mismatch) |
| Government warning — bold | A vision model can't certify typography, so this **never silently passes**: clearly-not-bold → mismatch, otherwise flagged for human confirmation |
| Image legibility | Poor photos (angle, glare, blur) downgrade a pass to "needs review" instead of guessing |

## Architecture & Key Decisions

**The Model Transcribes while the Code Decides.** Claude's only job is to read the
label and return each field *verbatim* (structured outputs guarantee parseable
JSON). Every compliance verdict comes from `app/comparison.py` — plain,
deterministic, unit-tested Python (32 tests). Rationale:

- The rules are auditable: a reviewer can read the exact logic that rejects a
  label, and it never drifts with model behavior.
- Dave's "you need judgment" concern is handled structurally: the engine has a
  middle tier (*needs review*) instead of forcing binary pass/fail, and the
  agent always makes the final call.
- Jenny's "the warning must be exact" requirement is a string comparison, not
  an LLM opinion.

**Latency Budget: ~5 seconds.** The previous vendor pilot died at 30–40s/label.
Choices made for speed:

- Default model is `claude-haiku-4-5` (fast vision model). Override with
  `LABEL_MODEL=claude-opus-4-8` if accuracy on difficult artwork matters more
  than latency.
- Images are downscaled to ≤1568 px before upload — full-resolution artwork
  adds tokens, not accuracy, at label sizes.
- One API call per label, no agentic loop.
- Batches run 4 labels concurrently; each result shows its own elapsed time so
  slow responses are visible, not mysterious.

**Batch Uploads** (Janet's ask): up to 300 images + one CSV
(`filename, brand_name, class_type, alcohol_content, net_contents`). Rows
without images and images without rows are reported individually rather than
failing the whole batch. Results are sorted problems-first.

**Universal UI for the Whole Team** (Dave to Jenny): one screen, two tabs, big type,
drag-and-drop, color-coded verdicts, no configuration. Plain HTML/JS — no
build step.

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required for live label reading |
| `LABEL_MODEL` | `claude-haiku-4-5` | Claude model for extraction |
| `LABEL_DEMO` | off | `1` = canned extractions for the bundled samples; no API calls |

## API

- `POST /api/verify` — multipart: `image` + form fields `brand_name`,
  `class_type`, `alcohol_content`, `net_contents` → `VerificationResult`
- `POST /api/verify-batch` — multipart: repeated `images` + `applications`
  (CSV) → per-file results + summary counts
- `GET /api/health` — mode/model info
- Interactive docs at `/docs` (FastAPI/OpenAPI)

## Deployment

Step-by-step guides for **Vercel** and **Replit** are in
[DEPLOYMENT.md](DEPLOYMENT.md). The repo already includes the config each one
needs (`vercel.json` + `api/index.py`, and `.replit`).

Also container-ready — any Docker host (Render, Fly.io, Railway, Azure App
Service):

```bash
docker build -t label-verifier .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... label-verifier
```

Note Marcus's firewall constraint: the only outbound dependency is
`api.anthropic.com`. For a production TTB deployment behind the agency
firewall, the same code can point at Claude on Azure-adjacent FedRAMP-
authorized channels (e.g., AWS GovCloud Bedrock) by swapping the client —
the extraction interface is one function.

## Assumptions & Trade-Offs

- **Prototype scope** (per Marcus): no auth, no persistence, nothing stored —
  uploads are processed in memory and discarded.
- **Beverage-type nuances** (wine ABV tolerance bands, malt beverage
  exceptions) are out of scope; the engine checks label-vs-application
  consistency, not every Part 5/7 rule. The comparison module is where those
  rules would slot in.
- **Bold detection is best-effort.** Typography can't be reliably certified
  from a photo, so the tool flags rather than passes when unsure.
- **Demo mode** exists so the workflow can be evaluated without credentials;
  it only recognizes the bundled sample filenames.
- Python 3.9-compatible on purpose (matches conservative government IT
  baselines; it's what ships on current macOS).

## Repository Layout

```
app/
  main.py         FastAPI routes (single + batch + health)
  extraction.py   Claude vision call — transcription only
  comparison.py   Deterministic verification engine (the rules)
  schemas.py      Pydantic models
  demo.py         Canned extractions for LABEL_DEMO=1
  static/         UI (vanilla HTML/CSS/JS)
scripts/generate_samples.py   Builds samples/*.png + applications.csv
samples/          Four test labels + matching applications CSV
tests/            32 unit tests for the verification engine
```
