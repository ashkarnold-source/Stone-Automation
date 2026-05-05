# Stone Command Center

Multi-channel outbound command center for home healthcare equity consulting.

## Features

- **Prospect database** — CSV import, pipeline stages, ownership/revenue filters
- **Outreach sequences** — Multi-touch cadences (email, LinkedIn, phone) with daily queue
- **Gmail integration** — Send emails and AI-draft with Claude
- **Events module** — Track conferences, attendee targeting, pre/post-event outreach
- **AI layer** — Claude-powered prospect briefs, email drafts, weekly digest

## Local Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy env file and fill in keys
cp .env.example .env

# 3. Run the app
uvicorn app.main:app --reload
```

Open http://localhost:8000

## Deploy to Railway

1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
3. Add a PostgreSQL database (Railway Add-ons → PostgreSQL)
4. Set environment variables in Railway dashboard (copy from `.env.example`)
5. Deploy — Railway auto-builds and runs `Procfile`

## Environment Variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | Auto-set by Railway PostgreSQL. Leave blank locally for SQLite. |
| `ANTHROPIC_API_KEY` | From [console.anthropic.com](https://console.anthropic.com) — enables AI features |
| `GMAIL_CLIENT_ID` | From Google Cloud Console OAuth2 credentials |
| `GMAIL_CLIENT_SECRET` | From Google Cloud Console OAuth2 credentials |
| `GMAIL_REDIRECT_URI` | Set to your Railway app URL + `/auth/gmail/callback` in production |
| `FROM_EMAIL` | Your Gmail address |
| `FROM_NAME` | Your name (Ashley Stennis) |

## Gmail Setup

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → Enable Gmail API
3. Create OAuth2 credentials (Web Application)
4. Add your Railway URL + `/auth/gmail/callback` as an authorized redirect URI
5. Add `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET` to Railway env vars
6. Visit `/auth/gmail` in the app to authorize

## CSV Import

Upload any CSV from LinkedIn Sales Navigator, Apollo, or a spreadsheet.
The system auto-maps common column names — see `/prospects/import` for the full list.
