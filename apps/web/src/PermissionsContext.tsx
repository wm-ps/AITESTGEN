import { createContext, useContext } from 'react'
import type { Role } from './api'

// The signed-in user's role, provided once by App so any component can ask
// "may this user change things?" without `user` being threaded through every
// prop chain. Hiding controls is for clarity only — the API refuses a
// viewer's writes on its own (`api.auth.block_viewer_writes`).
const PermissionsContext = createContext<Role>('member')

export const PermissionsProvider = PermissionsContext.Provider

// False for a viewer: hide every action that would change something
// (run, cancel, heal, generate, schedule, edit, delete, add).
export function useCanEdit(): boolean {
  return useContext(PermissionsContext) !== 'viewer'
}

export function useIsViewer(): boolean {
  return useContext(PermissionsContext) === 'viewer'
}
