// Stamp the built bundle with the commit it was built from.
//
// Runs after `astro build` and writes `git rev-parse --short HEAD` to
// dist/version.txt. The Python server serves that file at /version, so a live
// check can compare the running build against HEAD; with no stamp it answers
// 404, so a build that skipped this step can never pass for live.
import { execFileSync } from 'node:child_process'
import { existsSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const dist = fileURLToPath(new URL('./dist/', import.meta.url))
if (!existsSync(dist)) {
  // Fail loudly: a stamp with no bundle beside it would name a build that
  // does not exist.
  throw new Error(`stamp-version: ${dist} is missing; run astro build first`)
}

// execFileSync throws (non-zero exit) when git fails, which fails the build.
const hash = execFileSync('git', ['rev-parse', '--short', 'HEAD'], {
  cwd: fileURLToPath(new URL('.', import.meta.url)),
  encoding: 'utf8',
}).trim()
writeFileSync(`${dist}version.txt`, `${hash}\n`)
console.log(`stamp-version: dist/version.txt = ${hash}`)
