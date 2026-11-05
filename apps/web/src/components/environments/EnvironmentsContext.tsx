import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, type EnvironmentRead } from '../../api'

// One list of an application's environments, loaded once by Workspace and
// shared by everything that picks or shows one (the run, download and
// schedule dialogs, Application settings). The first entry is always the
// application's own (default) environment: `id` null, `is_default` true.
export type EnvironmentsValue = {
  environments: EnvironmentRead[]
  refresh: () => Promise<void>
  // Opens the one Add environment dialog Workspace hosts; `onAdded` is called
  // with the new environment so a picker can select it straight away.
  requestAdd: (onAdded?: (environment: EnvironmentRead) => void) => void
  // False for a viewer, and for an app that signs in with a saved SSO session
  // (there is nothing in the UI that could capture one per environment).
  canAdd: boolean
}

const EnvironmentsContext = createContext<EnvironmentsValue | null>(null)

export const EnvironmentsProvider = EnvironmentsContext.Provider

// Null outside Workspace — pickers then render nothing and the caller uses the
// default environment, exactly as before environments existed.
export function useEnvironments(): EnvironmentsValue | null {
  return useContext(EnvironmentsContext)
}

// Anything but a list (an unexpected response) is treated as "no list": the
// pickers then don't show and everything targets the default environment.
const asList = (rows: unknown): EnvironmentRead[] => (Array.isArray(rows) ? rows : [])

export function useEnvironmentList(applicationId: string) {
  const [environments, setEnvironments] = useState<EnvironmentRead[]>([])

  const refresh = useCallback(async () => {
    try {
      setEnvironments(asList(await api.listEnvironments(applicationId)))
    } catch {
      // Best-effort: with no list the pickers simply don't show, and every
      // run, download and schedule keeps targeting the default environment.
    }
  }, [applicationId])

  useEffect(() => {
    let cancelled = false
    api
      .listEnvironments(applicationId)
      .then((rows) => {
        if (!cancelled) setEnvironments(asList(rows))
      })
      .catch(() => {
        // see `refresh`
      })
    return () => {
      cancelled = true
    }
  }, [applicationId])

  return { environments, refresh }
}

// "production" → "Production", "staging-eu" → "Staging Eu". Short all-caps
// words ("UAT", "QA") are kept as typed. Display only; the stored name is untouched.
function toDisplayName(name: string): string {
  return name
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((word) =>
      word.length <= 4 && word === word.toUpperCase() ? word : word.charAt(0).toUpperCase() + word.slice(1).toLowerCase(),
    )
    .join(' ')
}

// "Production" — the environment name only, what every environment picker shows.
export function environmentLabel(environment: EnvironmentRead): string {
  return toDisplayName(environment.name)
}
