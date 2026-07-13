# HMH Analytics Screenshot Tool

Playwright script that captures all eight procurement-analytics tabs as PNG files.
Used for visual QA during development.

## Setup

```bash
cd tools/screenshots
cp .env.example .env        # fill in SCREENSHOT_EMAIL, SCREENSHOT_PASSWORD
npm install
npx playwright install chromium
```

## Usage

```bash
# Requires: both the HMH backend (port 8000) and frontend (port 5173) running locally.
node capture_analytics.js
```

Screenshots are written to `tools/screenshots/output/`. The output directory is gitignored.

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SCREENSHOT_EMAIL` | Yes | — | Login email for the HMH admin account |
| `SCREENSHOT_PASSWORD` | Yes | — | Login password |
| `SCREENSHOT_BASE_URL` | No | `http://localhost:5173` | Frontend base URL |

## Notes

- Credentials are read from environment variables only. Never hardcode them.
- The script logs `JWT obtained (not logged).` — the token itself is never printed.
- Output files are large PNG screenshots and are gitignored.
