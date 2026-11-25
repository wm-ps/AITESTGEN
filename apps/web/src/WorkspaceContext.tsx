import { createContext, Fragment, useCallback, useContext, useEffect, useRef, useState } from 'react'
import {
  PERSONAL_WORKSPACE,
  ROLE_LABEL,
  TEAM_ROLE_LABEL,
  api,
  setActiveWorkspace,
  type MyWorkspacesRead,
  type WorkspaceRead,
  type WorkspaceRole,
} from './api'

// The workspace the user is looking at: a team they belong to, or their personal
// one. Everything that lists applications is scoped to it (the API reads it from
// the X-Team-Id header, set here before any child renders), and switching
// remounts the whole app subtree, so nothing from the previous workspace —
// open application, drafts, polls — survives a switch.
export type WorkspaceValue = {
  data: MyWorkspacesRead
  active: WorkspaceRead
  switchTo: (id: string) => void
  /** Re-reads the list (team changes, application counts). */
  refresh: () => void
}

const WorkspaceContext = createContext<WorkspaceValue | null>(null)

// Null outside the provider (and while it loads), so components that only
// sometimes sit under it — and their tests — need no workspace.
export function useWorkspace(): WorkspaceValue | null {
  return useContext(WorkspaceContext)
}

const NAME_KEY = 'vantage.workspace.names'
const ROLES_KEY = 'vantage.workspace.roles'

function readStore(key: string): Record<string, string> {
  try {
    return JSON.parse(window.localStorage.getItem(key) ?? '{}') as Record<string, string>
  } catch {
    return {}
  }
}

function writeStore(key: string, value: Record<string, string>): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // private window / blocked storage: the toasts below just won't have names
  }
}

export const roleLabel = (role: WorkspaceRole): string =>
  role === 'super_admin' ? ROLE_LABEL.super_admin : TEAM_ROLE_LABEL[role]

// Remembers each team's name and the user's role in it, so a later visit can say
// "Your role in X changed to Y" or "You were removed from X".
function remember(data: MyWorkspacesRead, notify: (message: string) => void): void {
  const names = readStore(NAME_KEY)
  const roles = readStore(ROLES_KEY)
  const known = Object.keys(roles).length > 0
  for (const team of data.teams) {
    names[team.id] = team.name
    if (team.role) {
      if (known && roles[team.id] && roles[team.id] !== team.role) {
        notify(`Your role in ${team.name} changed to ${roleLabel(team.role)}`)
      }
      roles[team.id] = team.role
    }
  }
  writeStore(NAME_KEY, names)
  writeStore(ROLES_KEY, roles)
}

// Where a user lands with no remembered workspace: the Default team they were
// moved into when teams shipped (their existing applications live there), else
// their personal workspace.
function firstWorkspace(data: MyWorkspacesRead): string {
  return data.teams.find((team) => team.is_default)?.id ?? PERSONAL_WORKSPACE
}

export function WorkspaceProvider({
  notify,
  onSwitched,
  children,
}: {
  notify: (message: string) => void
  /** The caller returns to the Applications list (the open application belongs to the old workspace). */
  onSwitched: () => void
  children: React.ReactNode
}) {
  const [data, setData] = useState<MyWorkspacesRead | null | 'failed'>(null)
  const [activeId, setActiveId] = useState(PERSONAL_WORKSPACE)
  const dataRef = useRef(data)
  dataRef.current = data
  const activeIdRef = useRef(activeId)
  activeIdRef.current = activeId

  const fallBackToPersonal = useCallback(
    (lostId: string, loaded: MyWorkspacesRead) => {
      const name = readStore(NAME_KEY)[lostId]
      notify(`You were removed from ${name ?? 'that team'}. Opened your personal workspace.`)
      setActiveWorkspace(PERSONAL_WORKSPACE)
      setActiveId(PERSONAL_WORKSPACE)
      setData(loaded)
      api.rememberWorkspace(PERSONAL_WORKSPACE).catch(() => {})
      onSwitched()
    },
    [notify, onSwitched],
  )

  useEffect(() => {
    let cancelled = false
    api
      .getMyWorkspaces()
      .then((loaded) => {
        if (cancelled) return
        if (!loaded || !Array.isArray(loaded.teams) || !loaded.personal) {
          setData('failed')
          return
        }
        const wanted = loaded.last_workspace ?? firstWorkspace(loaded)
        const exists = wanted === PERSONAL_WORKSPACE || loaded.teams.some((team) => team.id === wanted)
        remember(loaded, notify)
        if (!exists) {
          fallBackToPersonal(wanted, loaded)
          return
        }
        setActiveWorkspace(wanted)
        setActiveId(wanted)
        setData(loaded)
      })
      .catch(() => {
        // Without the list the app still works unscoped (everything the user can see).
        if (!cancelled) setData('failed')
      })
    return () => {
      cancelled = true
    }
    // Once, at sign-in.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // A request was refused because the active team is no longer the user's.
  useEffect(() => {
    function lost() {
      const current = dataRef.current
      if (current && current !== 'failed') {
        api
          .getMyWorkspaces()
          .then((loaded) => fallBackToPersonal(activeIdRef.current, loaded))
          .catch(() => {})
      }
    }
    window.addEventListener('workspace:lost', lost)
    return () => window.removeEventListener('workspace:lost', lost)
  }, [fallBackToPersonal])

  const refresh = useCallback(() => {
    api
      .getMyWorkspaces()
      .then((loaded) => {
        setData(loaded)
        const stillThere =
          activeIdRef.current === PERSONAL_WORKSPACE || loaded.teams.some((team) => team.id === activeIdRef.current)
        if (!stillThere) fallBackToPersonal(activeIdRef.current, loaded)
      })
      .catch(() => {})
  }, [fallBackToPersonal])

  const switchTo = useCallback(
    (id: string) => {
      const loaded = dataRef.current
      if (!loaded || loaded === 'failed' || id === activeIdRef.current) return
      const target = id === PERSONAL_WORKSPACE ? loaded.personal : loaded.teams.find((team) => team.id === id)
      if (!target) return
      setActiveWorkspace(id)
      setActiveId(id)
      api.rememberWorkspace(id).catch(() => {})
      notify(target.kind === 'team' ? `Switched to ${target.name}` : 'Switched to your personal workspace')
      onSwitched()
    },
    [notify, onSwitched],
  )

  if (data === null) return null
  if (data === 'failed') return <>{children}</>

  const active = activeId === PERSONAL_WORKSPACE ? data.personal : (data.teams.find((t) => t.id === activeId) ?? data.personal)
  return (
    <WorkspaceContext.Provider value={{ data, active, switchTo, refresh }}>
      {/* The key remounts everything below on a switch. */}
      <Fragment key={activeId}>{children}</Fragment>
    </WorkspaceContext.Provider>
  )
}
