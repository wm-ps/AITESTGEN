// Allure 3 report plugin that renders the Vantage-styled report: one
// self-contained index.html (data, styles, script, logo and attachments all
// inlined), so it can be uploaded and opened as a single S3 object.
//
// Loaded by allurerc.mjs through `plugins.vantage.import`. Allure constructs
// the module's default export, then calls `done(context, store)` once every result has been read (the same contract
// as the built-in @allurereport/plugin-* packages).
import { readFile } from 'node:fs/promises'

import { buildReportModel } from './model.mjs'

const MB = 1024 * 1024
// ponytail: a single-file report has to inline every attachment, so large
// ones are capped and listed as "omitted" instead. A fuller version would
// publish the multi-file report directory and link attachments by URL.
const IMAGE_MAX_BYTES = 5 * MB
const TEXT_MAX_BYTES = 256 * 1024
const DOWNLOAD_MAX_BYTES = 20 * MB
const DOWNLOAD_BUDGET_BYTES = 60 * MB

const TEXT_TYPES = /^(text\/|application\/json$|application\/xml$)/

function readable(name, contentType) {
  // Playwright's own name for the ARIA snapshot it attaches on failure.
  if (name === 'error-context') return 'Page snapshot at failure'
  if (contentType === 'application/vnd.allure.playwright-trace') return 'Playwright trace'
  return name || 'Attachment'
}

function kindOf(contentType) {
  if (!contentType) return 'download'
  if (contentType.startsWith('image/')) return 'image'
  if (TEXT_TYPES.test(contentType)) return 'text'
  return 'download'
}

async function resolveAttachment(store, link, budget) {
  const contentType = link.contentType ?? 'application/octet-stream'
  const base = {
    id: link.id,
    name: readable(link.name, contentType),
    contentType,
    kind: kindOf(contentType),
    fileName: `${(link.name || 'attachment').replace(/[^\w.-]+/g, '_')}${link.ext ?? ''}`,
  }
  if (link.missed) return { ...base, kind: 'omitted', reason: 'File was not captured' }

  const file = await store.attachmentContentById(link.id)
  const buffer = file ? await file.asBuffer() : undefined
  if (!buffer) return { ...base, kind: 'omitted', reason: 'File was not captured' }
  const size = buffer.length

  if (base.kind === 'image' && size <= IMAGE_MAX_BYTES) {
    return { ...base, size, dataUri: `data:${contentType};base64,${buffer.toString('base64')}` }
  }
  if (base.kind === 'text' && size <= TEXT_MAX_BYTES) {
    return { ...base, size, text: buffer.toString('utf8') }
  }
  if (base.kind !== 'image' && size <= DOWNLOAD_MAX_BYTES && budget.remaining >= size) {
    budget.remaining -= size
    const downloadType = contentType === 'application/vnd.allure.playwright-trace' ? 'application/zip' : contentType
    return {
      ...base,
      kind: 'download',
      size,
      dataUri: `data:${downloadType};base64,${buffer.toString('base64')}`,
    }
  }
  return { ...base, kind: 'omitted', size, reason: 'Too large to include in this report' }
}

// The data block sits inside <script type="application/json">, so "<" is
// escaped to keep "</script>" in any error text from ending it early.
function embedJson(value) {
  return JSON.stringify(value).replace(/</g, '\\u003c')
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (ch) => `&#${ch.charCodeAt(0)};`)
}

export default class VantageReportPlugin {
  async done(context, store) {
    const results = await store.allTestResults({ includeRetries: false })
    const title = context.reportName || 'Test report'
    const model = buildReportModel({ title, results })

    const linksById = new Map()
    for (const tr of results) {
      for (const link of await store.attachmentsByTrId(tr.id)) linksById.set(link.id, link)
    }
    const budget = { remaining: DOWNLOAD_BUDGET_BYTES }
    const attachments = {}
    for (const journey of model.journeys) {
      for (const test of journey.tests) {
        for (const id of test.attachmentIds) {
          const link = linksById.get(id)
          if (link && !attachments[id]) attachments[id] = await resolveAttachment(store, link, budget)
        }
      }
    }

    const here = new URL('.', import.meta.url)
    const [template, logo] = await Promise.all([
      readFile(new URL('template.html', here), 'utf8'),
      readFile(new URL('logo.datauri.txt', here), 'utf8'),
    ])
    const html = template
      .replace('__VANTAGE_PAGE_TITLE__', () => escapeHtml(title))
      .replace('__VANTAGE_LOGO__', () => logo.trim())
      .replace('__VANTAGE_DATA__', () => embedJson({ ...model, attachments }))
    await context.reportFiles.addFile('index.html', Buffer.from(html, 'utf8'))
  }
}
