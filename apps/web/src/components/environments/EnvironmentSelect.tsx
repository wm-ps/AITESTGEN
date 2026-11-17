import { environmentLabel, useEnvironments } from './EnvironmentsContext'

const ADD_NEW = '__add_new_environment__'
const DEFAULT = '__default_environment__'

// The environment picker: the default first, then the extras, then "Add new
// environment". `value` is an environment id, null for the default. Renders
// nothing until the application's environments are loaded (or outside
// Workspace), in which case the caller simply targets the default.
export function EnvironmentSelect({
  value,
  onChange,
  label = 'Environment',
  row,
}: {
  value: string | null
  onChange: (environmentId: string | null) => void
  label?: string
  // Label on the left, picker on the right (Run tests dialog).
  row?: boolean
}) {
  const context = useEnvironments()
  if (!context || context.environments.length === 0) return null
  const { environments, canAdd, requestAdd } = context

  return (
    <label
      className="field"
      style={row ? { display: 'grid', gridTemplateColumns: '120px 1fr', alignItems: 'center', gap: 12 } : undefined}
    >
      <span style={row ? { fontSize: 14, color: 'var(--fg-2)' } : { fontSize: 12, fontWeight: 600, color: 'var(--fg-2)' }}>
        {label}
      </span>
      <select
        value={value ?? DEFAULT}
        onChange={(e) => {
          if (e.target.value === ADD_NEW) {
            requestAdd((added) => onChange(added.id))
            return
          }
          onChange(e.target.value === DEFAULT ? null : e.target.value)
        }}
      >
        {environments.map((environment) => (
          <option key={environment.id ?? DEFAULT} value={environment.id ?? DEFAULT}>
            {environmentLabel(environment)}
          </option>
        ))}
        {canAdd && <option value={ADD_NEW}>+ Add new environment</option>}
      </select>
    </label>
  )
}
