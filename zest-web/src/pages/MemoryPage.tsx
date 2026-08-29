import { useEffect, useState } from 'react'

import { AlertBanner } from '../components/workspace/AlertBanner'
import { MemoryPanel } from '../components/workspace/MemoryPanel'
import { MemorySettingsSection } from '../components/workspace/MemorySettingsSection'
import type { WorkspacePanelTab } from '../hooks/useWorkspacePanel'
import { listBaseMemories, listExperienceMemories } from '../services/appServerApi'
import { useAuthStore } from '../stores/useAuthStore'
import type { ConversationMemoryRecord } from '../types/workspace'

type MemoryTab = WorkspacePanelTab

const MEMORY_TABS: Array<{ id: MemoryTab; label: string }> = [
  { id: 'baseMemories', label: '基础记忆' },
  { id: 'experienceMemories', label: '经验记忆' },
]

function MemoryPageContent() {
  const [activeTab, setActiveTab] = useState<MemoryTab>('baseMemories')
  const [baseMemories, setBaseMemories] = useState<ConversationMemoryRecord[]>([])
  const [experienceMemories, setExperienceMemories] = useState<ConversationMemoryRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const currentUser = useAuthStore((state) => state.user)
  const currentUserId = currentUser?.id ?? ''

  const selectedMemoryTitle = activeTab === 'baseMemories' ? '基础记忆' : '经验记忆'
  const selectedMemoryCount = activeTab === 'baseMemories'
    ? baseMemories.length
    : experienceMemories.length

  const loadMemories = async (targetTab: MemoryTab) => {
    if (!currentUserId) {
      setBaseMemories([])
      setExperienceMemories([])
      setErrorMessage('')
      return
    }

    setLoading(true)
    setErrorMessage('')
    try {
      if (targetTab === 'baseMemories') {
        setBaseMemories(await listBaseMemories(currentUserId))
        return
      }

      setExperienceMemories(await listExperienceMemories(currentUserId))
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '加载记忆失败。')
      if (targetTab === 'baseMemories') {
        setBaseMemories([])
      } else {
        setExperienceMemories([])
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!currentUserId) {
      setBaseMemories([])
      setExperienceMemories([])
      setErrorMessage('')
      return
    }

    void loadMemories(activeTab)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentUserId])

  const handleTabChange = (tab: MemoryTab) => {
    setActiveTab(tab)
    void loadMemories(tab)
  }

  const pageDescription = '管理当前用户的基础记忆与经验记忆。记忆刷新仅在点击对应按钮或手动刷新时触发。'

  return (
    <div className="workspace-shell">
      <div className="aurora aurora-one" />
      <div className="aurora aurora-two" />

      {errorMessage && <AlertBanner message={errorMessage} onClose={() => setErrorMessage('')} />}

      <header className="topbar">
        <div className="topbar-copy">
          <span className="eyebrow">Memory Center</span>
          <h1>Memory Center</h1>
          <p>{pageDescription}</p>
        </div>
      </header>

      <main className="workspace-page-body memory-page-body">
        <MemorySettingsSection />
        <section className="panel panel-feature config-center-shell memory-page-shell">
          <div className="section-heading">
            <div>
              <h2>记忆资源</h2>
              <span className="section-note">{selectedMemoryTitle}</span>
            </div>
            <div className="config-center-actions">
              <span className="badge">{selectedMemoryCount} 条</span>
              <button
                type="button"
                className="ghost-button"
                onClick={() => void loadMemories(activeTab)}
                disabled={loading}
              >
                刷新
              </button>
            </div>
          </div>

          <div className="workspace-tab-list config-center-tabs">
            {MEMORY_TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={`workspace-tab ${activeTab === tab.id ? 'active' : ''}`}
                onClick={() => handleTabChange(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <p className="memory-page-inline-note">
            {activeTab === 'baseMemories'
              ? '左侧为基础记忆条目，右侧查看选中条目的完整内容。'
              : '左侧为经验记忆条目，右侧查看解决方案、元数据与执行轨迹。'}
          </p>

          {loading ? (
            <section className="memory-page-empty">
              <h2>正在加载记忆</h2>
              <p>稍等片刻，正在从后端拉取当前用户的记忆条目。</p>
            </section>
          ) : (
            <MemoryPanel
              className="memory-page-panel"
              selectedTab={activeTab}
              baseMemories={baseMemories}
              experienceMemories={experienceMemories}
            />
          )}
        </section>
      </main>
    </div>
  )
}

export function MemoryPage() {
  return <MemoryPageContent />
}
