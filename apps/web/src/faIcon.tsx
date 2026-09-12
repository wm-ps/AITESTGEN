import type { IconDefinition } from '@fortawesome/fontawesome-svg-core'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'

// Several call sites (GenerationLoader's `icon` prop, EmptyState illustrations)
// expect a `ComponentType<{ size?: number; color?: string }>` — the shape
// every lucide icon already had. FontAwesomeIcon takes no numeric `size`
// prop, so this adapts one Font Awesome icon definition into that same
// zero-config shape instead of repeating the wrapper at every call site.
export function faIcon(icon: IconDefinition) {
  return function Icon({ size = 16, color }: { size?: number; color?: string } = {}) {
    return <FontAwesomeIcon icon={icon} style={{ fontSize: size, color }} />
  }
}
