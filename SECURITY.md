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
accounts, no rate limiting and no database.

CORS in `backend/api/main.py` allows the two localhost origins, anything listed
in `ALLOWED_ORIGINS`, and any `*.vercel.app` host by pattern. There is no `*`
anywhere, and the pattern is matched with `re.fullmatch`, so it cannot be
prefixed by an attacker-controlled label.

**CORS is not a security control.** It stops a browser on someone else's page
from reading your API's responses. It stops nothing at all from `curl`. Anyone
who learns the deployed URL can call `/api/agent/chat` and spend your Gemini
and FortyGuard credits.

If you deploy this (see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)), take that
seriously:

- Use keys with a hard quota, never one attached to a billing account.
- Keep the URL out of anything indexable until the demo.
- Watch the provider dashboards for unexpected usage.
- Take the service down when the hackathon is over.

For anything beyond a hackathon, put an API key or a rate limiter in front of
`/api/agent/chat` first.

## Reporting a vulnerability

Open a GitHub issue for anything non-sensitive. For something that should not
be public, contact the maintainers privately through their GitHub profiles
rather than filing a public issue.
