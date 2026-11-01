import { afterEach } from 'vitest'

/** A fresh slot attached to the document, removed after each test. */
export function makeSlot(): HTMLElement {
  const slot = document.createElement('div')
  document.body.append(slot)
  return slot
}

afterEach(() => {
  document.body.replaceChildren()
})
