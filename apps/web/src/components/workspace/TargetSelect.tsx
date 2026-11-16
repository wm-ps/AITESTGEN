import { useState } from 'react'
import {
  BROWSER_OPTIONS,
  DEFAULT_VIEWPORT,
  MORE_VIEWPORT_PRESETS,
  VIEWPORT_LIMITS,
  VIEWPORT_PRESETS,
  formatViewport,
  sameViewport,
  viewportError,
  type Browser,
  type RunTarget,
  type Viewport,
} from '../../runTarget'
import { BrowserIcon } from './BrowserIcon'

const CUSTOM = 'custom'
const labelStyle = { fontSize: 12, fontWeight: 600, color: 'var(--fg-2)' } as const

const presetValue = (viewport: Viewport) => `${viewport.width}x${viewport.height}`
const ALL_PRESETS = [...VIEWPORT_PRESETS, ...MORE_VIEWPORT_PRESETS]

// Which browsers (one or more) and which one window size a run uses. The
// parent owns the target; an unusable custom size is reported by
// `viewportError(target.viewport)`, which the parent uses to disable Run/Save.
export function TargetSelect({
  value,
  onChange,
}: {
  value: RunTarget
  onChange: (target: RunTarget) => void
}) {
  const [custom, setCustom] = useState(!ALL_PRESETS.some((preset) => sameViewport(preset, value.viewport)))
  const [draft, setDraft] = useState({ width: String(value.viewport.width), height: String(value.viewport.height) })
  const error = custom ? viewportError(value.viewport) : null

  function toggleBrowser(browser: Browser) {
    const checked = value.browsers.includes(browser)
    // At least one browser stays selected.
    if (checked && value.browsers.length === 1) return
    onChange({
      ...value,
      browsers: checked ? value.browsers.filter((b) => b !== browser) : [...value.browsers, browser],
    })
  }

  function changeSize(selected: string) {
    if (selected === CUSTOM) {
      setCustom(true)
      onChange({ ...value, viewport: { width: Number(draft.width) || 0, height: Number(draft.height) || 0 } })
      return
    }
    setCustom(false)
    const preset = ALL_PRESETS.find((p) => presetValue(p) === selected)
    if (preset) {
      setDraft({ width: String(preset.width), height: String(preset.height) })
      onChange({ ...value, viewport: preset })
    }
  }

  function changeCustom(field: 'width' | 'height', text: string) {
    const next = { ...draft, [field]: text }
    setDraft(next)
    onChange({ ...value, viewport: { width: Number(next.width) || 0, height: Number(next.height) || 0 } })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
        <legend style={{ ...labelStyle, padding: 0 }}>Browsers</legend>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 6 }}>
          {BROWSER_OPTIONS.map((option) => (
            <label
              key={option.key}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer' }}
            >
              <input
                type="checkbox"
                checked={value.browsers.includes(option.key)}
                onChange={() => toggleBrowser(option.key)}
              />
              <BrowserIcon browser={option.key} size={18} />
              {option.label}
            </label>
          ))}
        </div>
        <span className="caption" style={{ display: 'block', fontSize: 12, marginTop: 6 }}>
          Safari runs the WebKit engine.
        </span>
      </fieldset>

      <label className="field">
        <span style={labelStyle}>Window size</span>
        <select
          value={custom ? CUSTOM : presetValue(value.viewport)}
          onChange={(e) => changeSize(e.target.value)}
        >
          {VIEWPORT_PRESETS.map((preset) => (
            <option key={presetValue(preset)} value={presetValue(preset)}>
              {formatViewport(preset)}
              {sameViewport(preset, DEFAULT_VIEWPORT) ? ' (default)' : ''}
            </option>
          ))}
          <optgroup label="More sizes">
            {MORE_VIEWPORT_PRESETS.map((preset) => (
              <option key={presetValue(preset)} value={presetValue(preset)}>
                {formatViewport(preset)}
              </option>
            ))}
          </optgroup>
          <option value={CUSTOM}>Custom size…</option>
        </select>
      </label>

      {custom && (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', alignItems: 'center', gap: 8 }}>
            <div className="field">
              <input
                type="number"
                inputMode="numeric"
                aria-label="Width"
                min={VIEWPORT_LIMITS.minWidth}
                max={VIEWPORT_LIMITS.maxWidth}
                placeholder="Enter width"
                value={draft.width}
                onChange={(e) => changeCustom('width', e.target.value)}
              />
            </div>
            <span aria-hidden="true">×</span>
            <div className="field">
              <input
                type="number"
                inputMode="numeric"
                aria-label="Height"
                min={VIEWPORT_LIMITS.minHeight}
                max={VIEWPORT_LIMITS.maxHeight}
                placeholder="Enter height"
                value={draft.height}
                onChange={(e) => changeCustom('height', e.target.value)}
              />
            </div>
          </div>
          {error && (
            <div role="alert" style={{ color: 'var(--danger)', fontSize: 12.5, marginTop: 6 }}>
              {error}
            </div>
          )}
        </div>
      )}

      {value.browsers.length > 1 && (
        <p className="caption" style={{ margin: 0, fontSize: 12.5 }}>
          Each test runs on {value.browsers.length} browsers.
        </p>
      )}
    </div>
  )
}
