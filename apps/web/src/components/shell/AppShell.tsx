import { useEffect, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faChartPie, faChevronRight, faGear, faLayerGroup, faPlus, faRightLeft, faUsers } from '@fortawesome/free-solid-svg-icons'
// Bell import dropped alongside the commented-out notifications icon below —
// restore both together once there's a real notification source.
import { api, type UserRead } from '../../api'
import { VantageBrand } from '../Brand'

// Vantage V2 redesign — left sidebar + top bar chrome, replacing the old
// TopBar-only nav (see _bmad-output/.../mockups/Vantage v2.html, sidebar
// section ~line 244-303).
export type ShellRoute = 'overview' | 'apps' | 'wizard' | 'settings' | 'team' | 'app'

// `icon` matches Workspace.tsx's existing nav-icon convention (a fixed-size,
// zero-prop render function) rather than accepting a `size` prop — every
// caller (Workspace's own tabs, journeys/scenarios owned by App.tsx) already
// renders its icon that way.
export type AppShellTab = {
  key: string
  label: string
  icon: () => React.JSX.Element
}

export type AppShellAppContext = {
  name: string
  tabs: AppShellTab[]
  activeTab: string
  onSelectTab: (key: string) => void
  onExit: () => void
}

function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('')
}

export function AppShell({
  user,
  route,
  crumb,
  onGoOverview,
  onGoApps,
  onAddApplication,
  onOpenSettings,
  onGoTeam,
  onLogout,
  app,
  children,
}: {
  user: UserRead
  route: ShellRoute
  /** Current screen's label, shown in the top bar. */
  crumb: string
  onGoOverview: () => void
  onGoApps: () => void
  onAddApplication: () => void
  onOpenSettings?: () => void
  onGoTeam?: () => void
  onLogout: () => void
  /** When set (route === 'app'), renders the sidebar's per-application tab section. */
  app?: AppShellAppContext
  children: React.ReactNode
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  // Sidebar "Applications" badge count — matches the prototype's nav badge
  // (navMonitor). A light one-shot fetch rather than threading the
  // Home/Overview screens' own application lists through every render of
  // this always-mounted shell.
  const [appCount, setAppCount] = useState<number | null>(null)
  useEffect(() => {
    let cancelled = false
    api
      .getHome()
      .then((rows) => {
        if (!cancelled) setAppCount(rows.length)
      })
      .catch(() => {
        // best-effort — badge just stays hidden
      })
    return () => {
      cancelled = true
    }
  }, [route])

  const navItemStyle = (active: boolean): React.CSSProperties => ({
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: active ? '7px 9px' : '8px 10px',
    borderRadius: 8,
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: active ? 600 : 500,
    background: active ? 'rgba(15,118,110,0.14)' : 'transparent',
    color: active ? 'var(--accent-2)' : 'var(--fg-3)',
    border: active ? '1px solid rgba(15,118,110,0.26)' : '1px solid transparent',
  })

  const sectionLabelStyle: React.CSSProperties = {
    fontSize: 10,
    fontWeight: 600,
    letterSpacing: '0.09em',
    textTransform: 'uppercase',
    color: 'var(--fg-5)',
    padding: '8px 10px 5px',
  }

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: 'var(--bg)' }}>
      <div
        style={{
          width: 236,
          flex: 'none',
          background: 'var(--bg-2)',
          borderRight: '1px solid var(--line)',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <button
          type="button"
          onClick={onGoApps}
          aria-label="Go to Applications"
          style={{
            height: 60,
            flex: 'none',
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '0 18px',
            background: 'none',
            border: 'none',
            borderBottom: '1px solid var(--line)',
            cursor: 'pointer',
            font: 'inherit',
            textAlign: 'left',
          }}
        >
          <VantageBrand markSize={22} />
        </button>

        <div style={{ padding: '14px 10px', display: 'flex', flexDirection: 'column', gap: 1, overflowY: 'auto', flex: 1 }}>
          <div style={sectionLabelStyle}>Global</div>
          <div style={navItemStyle(route === 'overview')} onClick={onGoOverview}>
            <FontAwesomeIcon icon={faChartPie} style={{ width: 16, fontSize: 13, textAlign: 'center' }} />
            <span style={{ flex: 1 }}>Overview</span>
          </div>
          <div style={navItemStyle(route === 'apps')} onClick={onGoApps}>
            <FontAwesomeIcon icon={faLayerGroup} style={{ width: 16, fontSize: 13, textAlign: 'center' }} />
            <span style={{ flex: 1 }}>Applications</span>
            {appCount != null && appCount > 0 && (
              <span style={{ fontSize: 10.5, fontWeight: 600, padding: '1px 7px', borderRadius: 1000, background: 'var(--chip)', color: 'var(--fg-3)' }}>
                {appCount}
              </span>
            )}
          </div>
          <div style={navItemStyle(route === 'wizard')} onClick={onAddApplication}>
            <FontAwesomeIcon icon={faPlus} style={{ width: 16, fontSize: 13, textAlign: 'center' }} />
            <span style={{ flex: 1 }}>Add application</span>
          </div>

          {app && (
            <>
              <div style={{ marginTop: 16, padding: '0 10px 5px', display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ ...sectionLabelStyle, padding: 0, flex: 1 }}>Application</span>
                <span
                  onClick={app.onExit}
                  title="Exit application"
                  style={{ fontSize: 10, color: 'var(--fg-4)', cursor: 'pointer' }}
                >
                  Exit
                </span>
              </div>
              <div
                onClick={app.onExit}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 9,
                  margin: '0 0 4px',
                  padding: '8px 10px',
                  borderRadius: 8,
                  border: '1px solid var(--border-2)',
                  background: 'var(--panel)',
                  cursor: 'pointer',
                }}
              >
                <span style={{ width: 6, height: 6, flex: 'none', borderRadius: 1000, background: 'var(--accent)' }} />
                <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, fontWeight: 600, color: 'var(--fg)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {app.name}
                </span>
                <FontAwesomeIcon icon={faRightLeft} style={{ fontSize: 9.5, color: 'var(--fg-4)' }} />
              </div>
              {app.tabs.map((tab) => {
                const active = tab.key === app.activeTab
                const Icon = tab.icon
                return (
                  <div key={tab.key} style={navItemStyle(active)} onClick={() => app.onSelectTab(tab.key)}>
                    <Icon />
                    <span style={{ flex: 1 }}>{tab.label}</span>
                  </div>
                )
              })}
            </>
          )}

          {/* Hidden while an Application is open — its own tab section above
              already fills the sidebar, and keeping Configuration too forces
              a scroll on small screens for no benefit (Team members/Settings
              are one click away via "Exit application" either way). */}
          {!app && (
            <>
              <div style={{ ...sectionLabelStyle, padding: '16px 10px 5px' }}>Configuration</div>
              {user.role === 'admin' && onGoTeam && (
                <div style={navItemStyle(route === 'team')} onClick={onGoTeam}>
                  <FontAwesomeIcon icon={faUsers} style={{ width: 16, fontSize: 13, textAlign: 'center' }} />
                  <span style={{ flex: 1 }}>Team members</span>
                </div>
              )}
              {onOpenSettings && (
                <div style={navItemStyle(route === 'settings')} onClick={onOpenSettings}>
                  <FontAwesomeIcon icon={faGear} style={{ width: 16, fontSize: 13, textAlign: 'center' }} />
                  <span style={{ flex: 1 }}>Settings</span>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <div
          style={{
            height: 60,
            flex: 'none',
            background: 'var(--bg-2)',
            borderBottom: '1px solid var(--line)',
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            padding: '0 22px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 500, flex: '1 1 auto', minWidth: 140, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            <span style={{ color: 'var(--fg-4)' }}>Workspace</span>
            <FontAwesomeIcon icon={faChevronRight} style={{ fontSize: 9, color: 'var(--fg-5)' }} />
            <span style={{ color: 'var(--fg-1)', overflow: 'hidden', textOverflow: 'ellipsis' }}>{crumb}</span>
          </div>
          <button
            type="button"
            onClick={onAddApplication}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              height: 34,
              padding: '0 14px',
              borderRadius: 8,
              background: 'var(--accent)',
              color: '#fff',
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
              boxShadow: 'var(--accent-glow)',
              flex: 'none',
              whiteSpace: 'nowrap',
              border: 'none',
              font: 'inherit',
            }}
          >
            <FontAwesomeIcon icon={faPlus} style={{ fontSize: 11 }} />
            Add application
          </button>
          <div style={{ width: 1, height: 24, background: 'var(--border-2)', flex: 'none' }} />
          {/* Notifications — no backing feature yet, commented out rather than
              shown as dead chrome on every page. Re-enable once there's a real
              notification source to point it at. */}
          {/* <Bell size={15} style={{ color: 'var(--fg-3)', flex: 'none' }} /> */}
          <div style={{ position: 'relative' }}>
            <button
              type="button"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((open) => !open)}
              style={{
                width: 30,
                height: 30,
                flex: 'none',
                borderRadius: 1000,
                background: 'var(--chip)',
                border: '1px solid var(--border-2)',
                color: 'var(--accent-2)',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              {initials(user.name)}
            </button>
            {menuOpen && (
              <>
                <div onClick={() => setMenuOpen(false)} style={{ position: 'fixed', inset: 0, zIndex: 40 }} aria-hidden="true" />
                <div
                  role="menu"
                  style={{
                    position: 'absolute',
                    right: 0,
                    top: 38,
                    minWidth: 180,
                    borderRadius: 10,
                    background: 'var(--panel)',
                    border: '1px solid var(--border-2)',
                    boxShadow: 'var(--panel-shadow)',
                    overflow: 'hidden',
                    zIndex: 41,
                  }}
                >
                  <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--line)' }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg)' }}>{user.name}</div>
                    <div style={{ fontSize: 12, marginTop: 1, color: 'var(--fg-4)' }}>{user.email}</div>
                  </div>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={onLogout}
                    style={{ display: 'block', width: '100%', textAlign: 'left', padding: '10px 14px', background: 'none', border: 'none', fontSize: 13, color: 'var(--bad)', cursor: 'pointer', fontFamily: 'inherit' }}
                  >
                    Log out
                  </button>
                </div>
              </>
            )}
          </div>
        </div>

        <div
          id="app-shell-scroll"
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '26px clamp(18px, 2.4vw, 40px) 44px',
            boxSizing: 'border-box',
            background:
              'radial-gradient(1200px 620px at 6% -12%, rgba(15,118,110,0.10), transparent 60%), radial-gradient(1000px 560px at 100% 0%, rgba(13,138,100,0.07), transparent 58%), linear-gradient(180deg, #F4F5F8 0%, #EAECF1 42%, #E4E7EE 100%)',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {children}
        </div>
      </div>
    </div>
  )
}
