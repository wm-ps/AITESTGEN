import { useEffect, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faFloppyDisk, faPen } from '@fortawesome/free-solid-svg-icons'
import { ApiError, api } from '../../api'
import { NotesFields, toNotesFormState, toNotesPayload, type NotesFormState } from '../NotesFields'
import { LoadingDots } from '../LoadingDots'
import { SkeletonRows } from '../Skeleton'

const panelStyle: React.CSSProperties = {
  background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
  backdropFilter: 'blur(16px) saturate(1.25)',
  border: '1px solid var(--border-1)',
  borderRadius: 14,
  boxShadow: 'var(--panel-shadow)',
  overflow: 'hidden',
}

export function NotesTab({ applicationId }: { applicationId: string }) {
  const [form, setForm] = useState<NotesFormState | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    let cancelled = false
    setForm(null)
    api
      .getApplication(applicationId)
      .then((application) => {
        if (!cancelled) setForm(toNotesFormState(application.application_context))
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof ApiError ? err.message : 'Failed to load notes.')
      })
    return () => {
      cancelled = true
    }
  }, [applicationId])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form) return
    setSaveError(null)
    setSaved(false)
    setSaving(true)
    try {
      const application = await api.updateApplicationContext(applicationId, toNotesPayload(form))
      setForm(toNotesFormState(application.application_context))
      setSaved(true)
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : 'Saving notes failed.')
    } finally {
      setSaving(false)
    }
  }

  if (loadError) {
    return (
      <div style={{ ...panelStyle, padding: 20 }}>
        <div style={{ color: 'var(--bad)', fontSize: 13 }} role="alert">
          {loadError}
        </div>
      </div>
    )
  }

  if (!form) {
    return (
      <div style={{ ...panelStyle, padding: 20 }} role="status">
        <SkeletonRows count={5} height={60} gap={16} />
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <form onSubmit={handleSubmit} style={panelStyle}>
        <fieldset disabled={saving} style={{ border: 0, margin: 0, padding: 0, display: 'contents' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '16px 20px',
              borderBottom: '1px solid var(--line)',
            }}
          >
            <FontAwesomeIcon icon={faPen} style={{ fontSize: 14, color: 'var(--accent)' }} />
            <span style={{ fontSize: 14.5, fontWeight: 600, color: 'var(--fg)' }}>Application context</span>
          </div>

          <div style={{ padding: 20 }}>
            <NotesFields form={form} onChange={setForm} />
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'flex-end',
              gap: 12,
              padding: '14px 20px',
              borderTop: '1px solid var(--line)',
            }}
          >
            {saveError && (
              <div style={{ color: 'var(--bad)', fontSize: 13, flex: 1 }} role="alert">
                {saveError}
              </div>
            )}
            {saved && <span style={{ fontSize: 12, color: 'var(--ok)' }}>Notes saved.</span>}
            <button
              type="submit"
              disabled={saving}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                height: 38,
                padding: '0 20px',
                borderRadius: 8,
                background: 'var(--accent)',
                color: '#fff',
                fontSize: 13.5,
                fontWeight: 600,
                cursor: saving ? 'default' : 'pointer',
                boxShadow: 'var(--accent-glow)',
                border: 'none',
                opacity: saving ? 0.75 : 1,
              }}
            >
              {saving ? (
                <LoadingDots label="Saving" />
              ) : (
                <>
                  <FontAwesomeIcon icon={faFloppyDisk} style={{ fontSize: 12 }} />
                  Save notes
                </>
              )}
            </button>
          </div>
        </fieldset>
      </form>
    </div>
  )
}
