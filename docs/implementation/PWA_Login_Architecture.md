# PWA and Login Architecture

## Root causes found

The previous manifest referenced missing 192px/512px icons. No service worker was registered, so there was no navigation fallback, cache lifecycle or understandable offline state. The production hostname fallback omitted `hmhgroup.co.za`. Login guards trusted a locally stored role and discarded the requested nested destination. A 401 from the login endpoint itself was handled like an expired application session, risking a reload loop. Direct routes depended entirely on hosting rewrites.

### Live deployment audit — 2026-08-02

- `https://hmhgroup.co.za/`, `/login`, `/site-login`, `/manifest.json` and `/sw.js` returned HTTP 404.
- `https://www.hmhgroup.co.za/` also returned HTTP 404.
- `https://app.hmhgroup.co.za/`, `/login` and `/site-login` returned HTTP 200 from Vercel.
- The app-subdomain manifest was the old build (`start_url: "/"`, no explicit scope).
- The app-subdomain `/sw.js`, `/icon-192.png` and `/icon-512.png` returned the 1,198-byte HTML app shell with `text/html`, not service-worker JavaScript or PNG files.

This confirms two separate causes: missing/misserved PWA assets in the deployed build, and an apex/www custom-domain mapping that is not serving the frontend. The repository fixes the first on deployment. Vercel/DNS must map or redirect the apex and www hosts before `https://hmhgroup.co.za/login` can work.

## Installed application

- Manifest ID/scope: `/`
- Start URL: `/login?source=pwa`
- Display: `standalone`
- Standard icons: 192x192 and 512x512
- Maskable icon: 512x512 with safe-area padding
- Apple touch icon: 180x180
- Theme/background are HMH navy.

The icons are deterministic raster derivatives of the existing HMH logo. No extra wordmark or synthetic symbol is introduced.

## Service-worker policy

| Request | Strategy | Stored data |
|---|---|---|
| HTML navigation | Network first, cached application shell fallback, then `offline.html` | Public `index.html` shell only |
| Hashed `/assets/*` | Cache first after first controlled load | Versioned JS/CSS/static assets |
| Same-origin `/api/*` | Never intercepted | Nothing |
| Cross-origin production API/auth | Never intercepted | Nothing |
| Non-GET request | Never intercepted | Nothing |

Old `hmh-*` caches are deleted during activation. A changed worker installs in waiting state. The UI offers “Update now”; only user acceptance sends `SKIP_WAITING`, then reloads once on controller change. Navigation remains network-first, so a normal redeploy does not pin stale HTML.

`_headers` and `vercel.json` serve `sw.js` with no-cache/no-store and allow root scope. Hashed assets are immutable. Render, Cloudflare/Netlify-style `_redirects`, and Vercel provide SPA fallback; real static files are served before the fallback.

## Login routing

- `/login` is the common office/universal entry point.
- `/site-login` deliberately remains compatible and retains the site phone/PIN mode.
- Authenticated users opening a login page are routed to the authorised portal.
- Protected navigation builds `?returnTo=<path+query>`; the value must be an internal path and cannot point to an auth route.
- After login or mandatory password change, role and requested destination are reconciled. Site roles can only return to `/site`; office roles cannot return to it.
- Both guards use the server-verified `/users/me` result from `AuthContext`, not a stale role string.
- A non-login 401 clears access, refresh and role keys, then uses `location.replace` with a retained destination. A failed `/auth/login` stays on the page and displays the credential error.
- Logout clears all three session keys.

Tokens remain in localStorage to preserve the existing installed-app session model. The service worker never caches token-bearing API responses. A valid token is revalidated on application start; an expired token is cleared by the 401 handler.

## Repeatable verification

`cd hmh-frontend && npm run test:pwa` uses the frontend Playwright dependency and checks:

1. direct `/login` and `/site-login`, including browser refresh;
2. logged-out nested Fuel URL retention and return after office login;
3. site-role redirect through the compatibility login;
4. manifest/icon metadata, service-worker control and an offline nested navigation fallback.

Manual release UAT should additionally install the deployed HTTPS site on Android and iOS, verify close/reopen, clear or expire the session, and deploy a new build to confirm the update prompt on real devices.

## Notification and Fuel evidence hardening

`/notifications/:notificationId` first obtains an access-checked server action URL, marks the alert read without acknowledging/resolving it, and then opens the record. A 401 uses the existing safe `returnTo`; a 403 stays authenticated and renders a clear denial instead of looping through login. Alert history includes read alerts.

Fuel camera evidence is compressed before multipart upload and exposes preview, retake, remove, progress, retry and duplicate-submit protection. The service worker does not intercept `/api/`, `/uploads/`, cross-origin storage URLs or non-GET uploads; a Playwright cache inspection covers private Fuel evidence.
