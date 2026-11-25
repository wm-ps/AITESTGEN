import { createContext, useContext } from 'react'
import type { AppRole } from './api'

// The signed-in user's role on the application that is open (null outside one),
// provided once by App so any component can ask "may this user change things?"
// without the role being threaded through every prop chain. Hiding controls is
// for clarity only — the API refuses what a role may not do on its own
// (`api.access`).
const PermissionsContext = createContext<AppRole | null>(null)

export const PermissionsProvider = PermissionsContext.Provider

// False for a viewer: hide every action that would change something
// (run, cancel, heal, generate, schedule, edit, delete, add).
export function useCanEdit(): boolean {
  return useContext(PermissionsContext) !== 'viewer'
}

export function useIsViewer(): boolean {
  return useContext(PermissionsContext) === 'viewer'
}

// True for an application admin: the only role that changes an application's
// settings (environments, credentials, test case generation) and its access.
export function useIsAdmin(): boolean {
  return useContext(PermissionsContext) === 'app_admin'
}
