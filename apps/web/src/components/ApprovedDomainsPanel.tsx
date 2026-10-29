import { useEffect, useState } from 'react'
import { ApiError, DOMAIN_IN_USE_CODE, api, type DomainRead } from '../api'
import { LoadingDots } from './LoadingDots'

const panelStyle: React.CSSProperties = {
  background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
  backdropFilter: 'blur(16px) saturate(1.25)',
  border: '1px solid var(--border-1)',
  borderRadius: 14,
  padding: 20,
  display: 'flex',
  flexDirection: 'column',
  gap: 10,
  boxShadow: 'var(--panel-shadow)',
}

const chipStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 8,
  height: 28,
  padding: '0 10px 0 12px',
  borderRadius: 1000,
  background: 'rgba(30,150,138,0.14)',
  color: 'var(--accent-2)',
  fontSize: 13,
  fontWeight: 500,
}

const MAX_NAMES_SHOWN = 3

function inUseMessage(domain: DomainRead): string {
  const names = domain.applications.map((a) => a.name)
  const shown = names.slice(0, MAX_NAMES_SHOWN).join(', ')
  const more = names.length > MAX_NAMES_SHOWN ? ` +${names.length - MAX_NAMES_SHOWN} more` : ''
  return `‘${domain.host}’ is used by ${shown}${more}. Delete those applications first, then you can remove this domain.`
}

export function ApprovedDomainsPanel() {
  const [domains, setDomains] = useState<DomainRead[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [newHost, setNewHost] = useState('')
  const [adding, setAdding] = useState(false)
  const [removing, setRemoving] = useState<string | null>(null)
  // One message under the field: a failed add, or why a chip can't be removed.
  const [message, setMessage] = useState<string | null>(null)

  function refresh(): Promise<DomainRead[] | null> {
    return api
      .listDomains()
      .then((rows) => {
        setDomains(rows)
        return rows
      })
      .catch((err) => {
        setLoadError(err instanceof ApiError ? err.message : 'Loading approved domains failed.')
        return null
      })
  }

  useEffect(() => {
    refresh()
  }, [])

  async function addDomain() {
    const host = newHost.trim().replace(/,$/, '')
    if (!host || adding) return
    setMessage(null)
    setAdding(true)
    try {
      await api.addDomain(host)
      setNewHost('')
      await refresh()
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Could not add this domain.')
    } finally {
      setAdding(false)
    }
  }

  async function removeDomain(domain: DomainRead) {
    if (removing) return
    setMessage(null)
    if (domain.applications.length > 0) {
      setMessage(inUseMessage(domain))
      return
    }
    setRemoving(domain.id)
    try {
      await api.deleteDomain(domain.id)
      await refresh()
    } catch (err) {
      if (err instanceof ApiError && err.message === DOMAIN_IN_USE_CODE) {
        // The list was stale — an application got onboarded since it loaded.
        const rows = await refresh()
        const fresh = rows?.find((d) => d.id === domain.id)
        setMessage(fresh ? inUseMessage(fresh) : 'This domain is in use by an application.')
      } else {
        setMessage(err instanceof ApiError ? err.message : 'Could not remove this domain.')
      }
    } finally {
      setRemoving(null)
    }
  }

  return (
    <section style={panelStyle} aria-label="Approved domains">
      <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--fg)' }}>Allowed Domains</div>

      {loadError ? (
        <div role="alert" style={{ fontSize: 12.5, color: 'var(--bad)' }}>
          {loadError}
        </div>
      ) : domains === null ? (
        <LoadingDots label="Loading" />
      ) : (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: 8,
            minHeight: 46,
            padding: '8px 12px',
            border: '1px solid var(--border-2)',
            borderRadius: 10,
            background: 'var(--panel)',
          }}
        >
          {domains.map((domain) => (
            <span key={domain.id} style={chipStyle}>
              {domain.host}
              <button
                type="button"
                aria-label={`Remove ${domain.host}`}
                disabled={removing !== null}
                onClick={() => removeDomain(domain)}
                style={{ border: 'none', background: 'transparent', color: 'inherit', cursor: 'pointer', fontSize: 15, lineHeight: 1, padding: 0 }}
              >
                ×
              </button>
            </span>
          ))}
          <input
            aria-label="Add a domain"
            value={newHost}
            disabled={adding}
            placeholder="Add a domain…"
            onChange={(e) => setNewHost(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ',') {
                e.preventDefault()
                addDomain()
              }
            }}
            style={{ flex: 1, minWidth: 160, border: 'none', outline: 'none', background: 'transparent', fontSize: 13.5, color: 'var(--fg-1)', fontFamily: 'inherit' }}
          />
          {(adding || removing !== null) && <LoadingDots label={adding ? 'Adding' : 'Removing'} />}
        </div>
      )}

      {message && (
        <div
          role="alert"
          style={{ display: 'flex', alignItems: 'flex-start', gap: 10, fontSize: 12.5, color: 'var(--bad)' }}
        >
          <span style={{ flex: 1 }}>{message}</span>
          <button
            type="button"
            aria-label="Dismiss"
            onClick={() => setMessage(null)}
            style={{ border: 'none', background: 'transparent', color: 'inherit', cursor: 'pointer', fontSize: 15, lineHeight: 1 }}
          >
            ×
          </button>
        </div>
      )}
    </section>
  )
}
