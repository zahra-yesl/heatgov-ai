# Security

HeatGov AI needs three API keys. None of them is in this repository, and none
of them should ever be.

## Required keys

| Variable | Used by | Where to get it | Cost |
|---|---|---|---|
| `FORTYGUARD_API_KEY` | `backend/data_pipeline/` — heatmaps and environmental parameters | <https://docs-api.fortyguard.com/docs> | Hackathon credits |
| `GEMINI_API_KEY` | `backend/agent/` — the conversational agent | <https://aistudio.google.com/apikey> | Free tier |
| `CENSUS_API_KEY` | `backend/data_pipeline/fetch_census.py` — ACS 2019 demographics | <https://api.census.gov/data/key_signup.html> | Free, emailed in about a minute |

`CENSUS_API_KEY` is not optional. A keyless request to the Census API returns an
HTML *"Missing Key"* page with **HTTP 200**, not an error — silently unusable
data rather than a failure you would notice.

## Setting them up

```bash
cp .env.example .env      # copy .env.example on Windows
# then edit .env and paste your real keys
```

`.env` is listed in `.gitignore` and must never be committed. `.env.example`
holds placeholders only and is the file that belongs in version control.

Nothing in the code reads a key from anywhere but the environment:
`backend/config.py` loads `.env` and every module imports from there.

## If you commit a key by accident

Deleting the file in a later commit is **not** enough — the value stays in the
git history and in every clone and fork.

1. **Revoke the key first**, at the provider. That is the only step that
   actually stops the leak.
2. Issue a replacement and put it in your local `.env`.
3. Only then worry about scrubbing history
   (`git filter-repo`, or delete and recreate the repository if it is young).

Assume any key pushed to a public repository is compromised within minutes:
GitHub is scanned continuously by bots looking for exactly this.

## Scope of this project

HeatGov AI is a hackathon prototype. It has no authentication, no user
accounts, and no database. The API is meant to be reachable only from
`localhost`, and CORS is restricted accordingly in `backend/api/main.py`:

```python
allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"]
```

Do not expose the backend to the public internet as it stands. It would let
anyone spend your FortyGuard and Gemini credits through `/api/agent/chat`.

## Reporting a vulnerability

Open a GitHub issue for anything non-sensitive. For something that should not
be public, contact the maintainers privately through their GitHub profiles
rather than filing a public issue.
