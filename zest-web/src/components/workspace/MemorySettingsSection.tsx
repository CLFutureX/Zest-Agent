import { useEffect, useState } from 'react'
import { useAuthStore } from '../../stores/useAuthStore'
import { getMemorySettings, updateMemorySettings } from '../../services/appServerApi'
import type { MemorySettingsSummary } from '../../services/appServerApi'

type SettingItemProps = {
  title: string
  description: string
  enabled: boolean
  disabled: boolean
  onToggle: (enabled: boolean) => void
}

function SettingItem({ title, description, enabled, disabled, onToggle }: SettingItemProps) {
  return (
    <article className="config-card config-card-interactive memory-settings-item">
      <div className="config-card-header">
        <div>
          <strong>{title}</strong>
          <span>{enabled ? '已启用' : '未启用'}</span>
        </div>
        <button
          type="button"
          className={`config-toggle ${enabled ? 'is-enabled' : ''}`}
          aria-label={`${enabled ? '关闭' : '启用'} ${title}`}
          aria-pressed={enabled}
          disabled={disabled}
          onClick={() => onToggle(!enabled)}
        >
          <span className="config-toggle-thumb" />
        </button>
      </div>
      <p>{description}</p>
    </article>
  )
}

/**
 * 记忆设置：控制「后续新创建会话」是否启用基础记忆 / 经验记忆。
 * 配置持久化在 app-server（按用户存一条），创建会话时由后端读取并注入，无需前端透传。
 */
export function MemorySettingsSection() {
  const currentUserId = useAuthStore((state) => state.user?.id ?? '')
  const [settings, setSettings] = useState<MemorySettingsSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!currentUserId) {
      setSettings(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    getMemorySettings(currentUserId)
      .then((data) => {
        if (!cancelled) setSettings(data)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [currentUserId])

  const handleToggle = async (key: 'enable_base_memory' | 'enable_experience_memory', value: boolean) => {
    if (!currentUserId || !settings || saving) return
    const previous = settings
    // 乐观更新
    setSettings({ ...settings, [key]: value })
    setSaving(true)
    setError(null)
    try {
      const next = await updateMemorySettings({
        userId: currentUserId,
        enableBaseMemory: key === 'enable_base_memory' ? value : previous.enable_base_memory,
        enableExperienceMemory: key === 'enable_experience_memory' ? value : previous.enable_experience_memory,
      })
      setSettings(next)
    } catch (err: unknown) {
      // 回滚
      setSettings(previous)
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  const baseEnabled = settings?.enable_base_memory ?? true
  const expEnabled = settings?.enable_experience_memory ?? true
  const disabled = loading || saving || !settings

  return (
    <section className="panel memory-settings-panel">
      <div className="section-heading">
        <div>
          <h2>记忆设置</h2>
          <span className="section-note">控制后续新创建会话是否启用记忆能力</span>
        </div>
        <span className="badge">已登录用户</span>
      </div>
      <p className="memory-page-inline-note">
        开启后，新建会话时将加载并写入对应记忆；关闭后，对应记忆不参与检索与写入。下方可查看当前已有的记忆条目。
      </p>
      {loading && <p className="memory-page-inline-note">正在加载设置…</p>}
      {error && <p className="memory-page-inline-note" style={{ color: '#d33' }}>设置同步失败：{error}</p>}
      <div className="config-center-grid memory-settings-grid">
        <SettingItem
          title="基础记忆"
          description="用户画像、偏好、领域知识与项目上下文。开启后会在会话中按分类加载与维护。"
          enabled={baseEnabled}
          disabled={disabled}
          onToggle={(v) => handleToggle('enable_base_memory', v)}
        />
        <SettingItem
          title="经验记忆"
          description="基于向量检索的排查经验与执行策略沉淀。开启后会按用户问题检索相似经验并写入。"
          enabled={expEnabled}
          disabled={disabled}
          onToggle={(v) => handleToggle('enable_experience_memory', v)}
        />
      </div>
    </section>
  )
}
