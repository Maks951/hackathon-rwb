# Platform frontend

Angular application for creating projects and monitoring generation runs.
Use Node.js 22.12 or later in the 22.x release line, or Node.js 24, and npm.

From the repository root (PowerShell or a shell):

```sh
cd apps/hackathon-rwb-angular
npm ci
npm start
```

Open http://localhost:4200/app/home. Start the platform API separately on port
8000. This branch contains frontend code only: it cannot start the API, database,
or generation worker. Development requests to `/api/v1/**` use the Angular proxy
in `src/proxy.conf.json`; change its target if the API uses another port.
No mock API or login flow is implemented in this branch. Authentication must be
implemented together with the backend before protecting these routes.

```sh
npm run build
npm test -- --watch=false
```

Production output is in `dist/hackathon-rwb-angular/browser`. The hosting server
must forward `/api/**` to the platform API and fall back to `index.html` for app
routes. Keep API routing ahead of the SPA fallback. Do not serve API requests as
HTML. Production builds do not provide a backend proxy themselves.

## Fixed in incorrect-frontend

- Correct bootstrap component; remove routes/imports for missing auth files.
- Redirect `/`, `/app`, and unknown routes to the project list.
- Use real API calls with a relative URL and a recursive development proxy rule.
- Reject names/requirements containing only whitespace before submission.
- Monitor runs without overlapping polls, with a 10 second request timeout,
  error recovery, and teardown on navigation. Changing run/project URL parameters
  reloads the corresponding data.
- Report event errors, avoid duplicate events across polls, and support retrying
  artifact loads. Load available artifacts for failed runs as well as successful
  runs. Cancel stale artifact/view requests when navigating away.
- Preserve the idempotency key when retrying an unsuccessful start request.
- Show structured API errors, including nested `error` envelopes.
- Use prebuilt Bootstrap CSS instead of recompiling deprecated third party Sass.
- Repair bootstrap, Bootstrap dependency, service worker build configuration,
  and obsolete tests in `templates/angular-admin`.

## Verification and remaining integration check

Both applications build in production mode. Platform unit/component tests cover
navigation, input validation, idempotency, timeouts, non-overlapping polls,
completion, event errors, artifact retries, and route changes. The template shell
also has a passing test. The development proxy is checked against a temporary
local HTTP backend.

The actual team API/worker is not included in this branch, so end-to-end
compatibility with it is not verified. The frontend's DTOs and endpoints have not
been changed based on assumptions. With the real stack running, check:

1. Create a project and open it.
2. Start a run and verify statuses, steps and event updates.
3. Check both success and failure results; open artifacts and download the ZIP.
4. Refresh a nested URL and temporarily stop/restart the API to check recovery.

A full browser test was not completed in this environment because the Chromium
binary was unavailable and its download failed. Unit/component tests use jsdom.
