# angular-pwa
Host for model-generated domain pages. The generator MUST emit
`src/app/generated/routes.ts` exporting `generatedRoutes: Routes` and all referenced components.
There is intentionally no successful empty fallback. All API calls use relative `/api/v1/` URLs.
Dependency versions come from package-lock.json, not a model response.
`npm ci` then `npm run build` after generation. Service worker caches static assets only.
