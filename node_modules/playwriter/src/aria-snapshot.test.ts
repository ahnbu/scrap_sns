import { describe, it, beforeAll, afterAll } from 'vitest'
import { Page } from 'playwright-core'
import fs from 'node:fs'
import path from 'node:path'
import { compactSnapshot, interactiveSnapshot, deduplicateSnapshot, getAriaSnapshot } from './aria-snapshot.js'
import { setupTestContext, cleanupTestContext, type TestContext } from './test-utils.js'

const TEST_PORT = 19986
const SNAPSHOTS_DIR = path.join(import.meta.dirname, 'aria-snapshots')

describe('aria-snapshot compression', () => {
  let ctx: TestContext
  let page: Page

  beforeAll(async () => {
    ctx = await setupTestContext({ port: TEST_PORT, tempDirPrefix: 'aria-snapshot-test-' })
    page = await ctx.browserContext.newPage()
    if (!fs.existsSync(SNAPSHOTS_DIR)) {
      fs.mkdirSync(SNAPSHOTS_DIR, { recursive: true })
    }
  }, 60000)

  afterAll(async () => {
    await cleanupTestContext(ctx)
  })

  const sites = [
    { name: 'hackernews', url: 'https://news.ycombinator.com' },
    { name: 'github', url: 'https://github.com' },
  ]

  const formats = [
    { name: 'raw', transform: (s: string) => s },
    { name: 'compact', transform: (s: string) => compactSnapshot(s) },
    { name: 'interactive', transform: (s: string) => interactiveSnapshot(s) },
    { name: 'interactive-dedup', transform: (s: string) => deduplicateSnapshot(interactiveSnapshot(s)) },
    { name: 'interactive-flat', transform: (s: string) => interactiveSnapshot(s, { keepStructure: false }) },
  ]

  for (const site of sites) {
    it(`${site.name} - compression stats`, async () => {
      await page.goto(site.url, { waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(1000)

      const { snapshot } = await getAriaSnapshot({ page })
      const rawSize = snapshot.length

      console.log(`\n📊 ${site.name.toUpperCase()} compression stats:`)

      for (const format of formats) {
        const processed = format.transform(snapshot)
        const size = processed.length
        const savings = format.name === 'raw' ? 0 : Math.round((1 - size / rawSize) * 100)

        fs.writeFileSync(path.join(SNAPSHOTS_DIR, `${site.name}-${format.name}.txt`), processed)

        const savingsStr = format.name === 'raw' ? '(baseline)' : `${savings}% smaller`
        console.log(`  ${format.name}: ${size} bytes ${savingsStr}`)
      }
    }, 30000)
  }
})
