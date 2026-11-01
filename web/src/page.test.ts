// @vitest-environment node
import { experimental_AstroContainer as AstroContainer } from 'astro/container'
import { describe, expect, it } from 'vitest'
import Index from './pages/index.astro'
import { SHELL } from './test/shell'

async function html(): Promise<string> {
  const container = await AstroContainer.create()
  return container.renderToString(Index)
}

describe('index.astro', () => {
  it('renders the page shell with a title and a heading', async () => {
    const page = await html()
    expect(page).toContain('<title>Screen Locker — status</title>')
    expect(page).toContain('<h1>Screen locker</h1>')
    expect(page).toContain('lang="en"')
  })

  it('renders the three hidden card shells with their slots', async () => {
    const page = await html()
    for (const name of ['now', 'health', 'why']) {
      expect(page).toMatch(
        new RegExp(`<section[^>]*data-card="${name}"[^>]*hidden`),
      )
    }
    expect(page.match(/data-slot/g)).toHaveLength(3)
  })

  it('renders the loading line and a hidden alert region', async () => {
    const page = await html()
    expect(page).toContain('Reading status…')
    expect(page).toMatch(/<div[^>]*role="alert"[^>]*data-errors[^>]*hidden/)
  })
})

/** Tag name plus sorted attribute names, for every tag carrying a data-* hook. */
function hooks(markup: string): string[] {
  return (markup.match(/<[a-z0-9]+(?:\s[^>]*)?\sdata-[^>]*>/g) ?? []).map((tag) => {
    const name = /^<([a-z0-9]+)/.exec(tag)?.[1] ?? ''
    const attrs = [...tag.matchAll(/\s([a-z-]+)(?==|\s|>)/g)].map((m) => m[1])
    return `${name} ${attrs.sort().join(' ')}`
  })
}

describe('test shell', () => {
  it('has the same data-* hooks as the real page', async () => {
    expect(hooks(SHELL).sort()).toEqual(hooks(await html()).sort())
  })
})
