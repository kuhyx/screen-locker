/// <reference types="astro/client" />

declare module '*.astro' {
  import type { AstroComponentFactory } from 'astro/runtime/server/index.js'

  const component: AstroComponentFactory
  export default component
}

/// <reference path="../node_modules/@kuhyx/kuhy-credit/src/kuhy-credit.d.ts" />
