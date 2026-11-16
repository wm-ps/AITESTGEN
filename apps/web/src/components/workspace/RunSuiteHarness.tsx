import { useState } from 'react'
import { DEFAULT_TARGET, type RunTarget } from '../../runTarget'
import { RunSuiteButton } from './RunSuiteButton'

// Test-only stand-in for Workspace: owns the Run tests dialog's state the way
// Workspace does and reports each mode choice with the environment and target
// that were picked.
export function RunSuiteHarness({
  onFullSuite = () => {},
  onOpenJourneysDialog = () => {},
  onOpenSuitesDialog = () => {},
}: {
  onFullSuite?: (environmentId: string | null, target: RunTarget) => void
  onOpenJourneysDialog?: (environmentId: string | null, target: RunTarget) => void
  onOpenSuitesDialog?: (environmentId: string | null, target: RunTarget) => void
}) {
  const [open, setOpen] = useState(false)
  const [environmentId, setEnvironmentId] = useState<string | null>(null)
  const [target, setTarget] = useState<RunTarget>(DEFAULT_TARGET)
  return (
    <>
      <RunSuiteButton
        running={false}
        open={open}
        onOpenChange={setOpen}
        environmentId={environmentId}
        onEnvironmentChange={setEnvironmentId}
        target={target}
        onTargetChange={setTarget}
        onFullSuite={() => onFullSuite(environmentId, target)}
        onOpenJourneysDialog={() => onOpenJourneysDialog(environmentId, target)}
        onOpenSuitesDialog={() => onOpenSuitesDialog(environmentId, target)}
      />
      {/* What Workspace does for a sub-dialog's Back button. */}
      <button type="button" onClick={() => setOpen(true)}>
        Back to Run tests
      </button>
    </>
  )
}
