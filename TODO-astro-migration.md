# Migrate screen-locker/web to Astro (no React)

## what
The status page in `web/` (now/health/why cards, polling `/api/status`)
becomes one Astro 7 static page. Its `<script>` polls and renders in vanilla
TS. `python -m screen_locker._web_server` keeps serving `web/dist` on
127.0.0.1:8770.

## steps
1. Do `~/src/utils/web_ui/TODO-astro-port.md` first. Then add `@kuhyx/web-ui`
   at the new tag, for `tokens.css` only. This repo does not use it yet.
2. Use a single page, `src/pages/index.astro`. There is no routing today, so
   `_web_server.py` and its SPA fallback need no change.
3. Rewrite the four React files:
   - `App.tsx` becomes `index.astro` plus `layouts/Base.astro`.
   - `components/NowCard.tsx`, `HealthCard.tsx` and `WhyTable.tsx` become `.astro`
     shells with `data-*` slots, filled by a renderer in `src/render.ts`.
   - Hook `useStatusPoll.ts` becomes `src/poll.ts`, a plain poller class with
     `start()`, `stop()` and a callback. It stops on `visibilitychange`
     hidden, as now.
   - `api.ts`, `format.ts` and `types.ts` stay as they are.
4. The `<script>` in `index.astro` only wires `poll.ts` to `render.ts`. The
   logic stays in `.ts` files so the coverage thresholds still apply.
5. Dependencies, from `web/`, exact pins via pnpm:
   - Add `astro@7.4.4`, `@astrojs/check@0.9.12` and `eslint-plugin-astro@3.2.1`.
   - Remove `react`, `react-dom`, `@vitejs/plugin-react`,
     `@testing-library/react`, `eslint-plugin-react-hooks` and
     `eslint-plugin-react-refresh`.
   - Drop direct `vite` (Astro brings `^8.3.5`).
   - Fold `tsconfig.app.json`, `tsconfig.node.json` and `tsconfig.test.json`
     into Astro's `tsconfig` preset where possible.
6. Tests. Use vitest 5.0.5 with `getViteConfig()`:
   - `render.ts` and `poll.ts` are tested in jsdom with `@testing-library/dom`
     and fake timers.
   - `src/test/factories.ts` stays.
   - One Container API test checks that the page shell renders.
7. `build` becomes `astro check && astro build`, output `web/dist`.
8. There is no `[agent_ready]` table. It is a loopback status page, so skip
   AgentReady.

## done
Run from `web/`:
`pnpm install --frozen-lockfile && pnpm lint && pnpm coverage && pnpm build`
Then:
`! grep -q '"react"' package.json && ! grep -qE '"(react-dom|@vitejs/plugin-react)"' package.json && ! find src -name '*.tsx' | grep -q .`
Both exit 0. The Python web-server tests still pass:
`python -m pytest -q screen_locker/tests/test_web_server.py screen_locker/tests/test_web_server_part2.py`

## verify
Run `systemctl --user restart screen-locker-web.service`. Then:
- `curl -s http://127.0.0.1:8770/ | grep -q '<h1'`
- Use a headless chromium at 4K and at mobile size. All three cards fill
  within one poll, and there are no console errors.

## read first
- `~/src/utils/web_ui/TODO-astro-port.md` (do it first)
- `web/src/App.tsx`, `web/src/useStatusPoll.ts`, `web/src/api.ts`
- `screen_locker/_web_server.py`, `screen-locker-web.service`

REMOVE ME AFTER FINISH
