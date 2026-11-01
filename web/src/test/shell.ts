/** Hand-kept copy of the page's `data-*` hooks; page.test.ts fails if it drifts. */
export const SHELL = `
<main>
  <div class="error" role="alert" data-errors hidden></div>
  <p class="muted" data-loading>Reading status…</p>
  <section class="card" aria-labelledby="now-heading" data-card="now" hidden>
    <h2 id="now-heading">Now</h2>
    <div data-slot></div>
  </section>
  <section class="card" aria-labelledby="health-heading" data-card="health" hidden>
    <h2 id="health-heading">Health</h2>
    <div data-slot></div>
  </section>
  <section class="card" aria-labelledby="why-heading" data-card="why" hidden>
    <h2 id="why-heading">Why</h2>
    <div data-slot></div>
  </section>
</main>`
