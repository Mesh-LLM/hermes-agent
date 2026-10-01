import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { controlMeshLlmClient, getMeshLlmClientStatus, type MeshLlmClientStatus } from '@/hermes'
import { useI18n } from '@/i18n'
import { Globe } from '@/lib/icons'
import { notifyError } from '@/store/notifications'

import { SettingsContent, SettingsSection, SettingsSkeleton } from './primitives'
import { SettingsProfileScope } from './profile-scope'

export function MeshLlmSettings({ profile }: { profile?: string }) {
  const { t } = useI18n()
  const copy = t.settings.meshllm
  const [status, setStatus] = useState<MeshLlmClientStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const generation = useRef(0)
  const statusRequest = useRef(0)
  const controlPending = useRef(false)

  useEffect(() => {
    let active = true
    ++generation.current
    ++statusRequest.current
    controlPending.current = false
    setStatus(null)
    setError(null)
    setBusy(false)

    const update = async () => {
      if (controlPending.current) return
      const requestGeneration = generation.current
      const requestId = ++statusRequest.current

      try {
        const next = await getMeshLlmClientStatus(profile)

        if (
          active &&
          !controlPending.current &&
          requestGeneration === generation.current &&
          requestId === statusRequest.current
        ) {
          setStatus(next)
          setError(null)
        }
      } catch (reason) {
        if (
          active &&
          !controlPending.current &&
          requestGeneration === generation.current &&
          requestId === statusRequest.current
        ) {
          setError(reason instanceof Error ? reason.message : String(reason))
        }
      }
    }

    void update()
    const timer = window.setInterval(() => void update(), 10_000)

    return () => {
      active = false
      ++generation.current
      ++statusRequest.current
      window.clearInterval(timer)
    }
  }, [profile])

  async function control(action: 'start' | 'stop' | 'restart') {
    const actionGeneration = ++generation.current
    ++statusRequest.current
    controlPending.current = true
    setBusy(true)

    try {
      const next = await controlMeshLlmClient(action, profile)

      if (actionGeneration === generation.current) {
        setStatus(next)
        setError(null)
      }
    } catch (reason) {
      if (actionGeneration !== generation.current) {
        return
      }

      notifyError(reason, copy.actionFailed)
      setError(reason instanceof Error ? reason.message : String(reason))

      try {
        const next = await getMeshLlmClientStatus(profile)

        if (actionGeneration === generation.current) {
          setStatus(next)
        }
      } catch {
        // Preserve the action error; the next poll can retry the status read.
      }
    } finally {
      if (actionGeneration === generation.current) {
        controlPending.current = false
        ++statusRequest.current
        setBusy(false)
      }
    }
  }

  if (!status && !error) {
    return <SettingsSkeleton sections={[{ rows: 3 }]} />
  }

  const state = status?.state ?? 'error'
  const stateLabel = copy.states[state]
  const models = status?.models ?? []

  return (
    <SettingsContent>
      <SettingsProfileScope className="mb-5" />
      <SettingsSection icon={Globe} title={copy.title}>
        <div className="grid gap-3 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="font-medium text-(--ui-text-primary)">{stateLabel}</p>
              <p className="text-(--ui-text-secondary)">
                {status?.connected ? copy.peers(status.peer_count) : copy.notConnected}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                disabled={busy || state === 'unconfigured' || state === 'connected'}
                onClick={() => void control('start')}
                size="sm"
                variant="secondary"
              >
                {copy.start}
              </Button>
              <Button
                disabled={busy || state === 'unconfigured' || state === 'stopped'}
                onClick={() => void control('stop')}
                size="sm"
                variant="secondary"
              >
                {copy.stop}
              </Button>
              <Button
                disabled={busy || state === 'unconfigured'}
                onClick={() => void control('restart')}
                size="sm"
                variant="secondary"
              >
                {copy.restart}
              </Button>
            </div>
          </div>
          {(error || status?.error) && (
            <p className="text-(--ui-text-secondary)" role="alert">
              {error || status?.error}
            </p>
          )}
          {state === 'unconfigured' && <p className="text-(--ui-text-secondary)">{copy.configureHint}</p>}
        </div>
      </SettingsSection>
      <SettingsSection icon={Globe} title={copy.modelsTitle}>
        {models.length > 0 ? (
          <ul className="grid gap-1 text-sm text-(--ui-text-primary)">
            {models.map(model => (
              <li className="py-1" key={model}>
                {model}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-(--ui-text-secondary)">{copy.noModels}</p>
        )}
      </SettingsSection>
    </SettingsContent>
  )
}
