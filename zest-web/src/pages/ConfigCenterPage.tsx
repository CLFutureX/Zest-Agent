import { useEffect, useMemo, useState } from 'react'

import {
  createLlmConfig,
  createPrompt,
  createSkill,
  createSubAgentConfig,
  listLlmConfigs,
  listPrompts,
  listSkills,
  listSubAgentConfigs,
  updatePrompt,
  updateSkill,
  updateSubAgentConfig,
} from '../services/appServerApi'
import { useAuthStore } from '../stores/useAuthStore'
import type {
  PromptConfigSummary,
  SkillProfileSummary,
  SubAgentConfigSummary,
  UserLlmConfigSummary,
} from '../types/workspace'
import { requestAuthDialog } from '../utils/authEvents'

type ConfigTab = 'llms' | 'skills' | 'prompts' | 'subagents'

export function ConfigCenterPage() {
  const currentUser = useAuthStore((state) => state.user)
  const currentUserId = currentUser?.id ?? ''
  const isGuest = !currentUserId
  const [activeTab, setActiveTab] = useState<ConfigTab>('llms')
  const [loading, setLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const [llmConfigs, setLlmConfigs] = useState<UserLlmConfigSummary[]>([])
  const [skills, setSkills] = useState<SkillProfileSummary[]>([])
  const [prompts, setPrompts] = useState<PromptConfigSummary[]>([])
  const [subagents, setSubagents] = useState<SubAgentConfigSummary[]>([])

  const [llmForm, setLlmForm] = useState({ usageId: '', model: '', apiKey: '', baseUrl: '' })

  const createEmptySkillForm = () => ({
    name: '',
    content: '',
    description: '',
    source: '',
    enabled: true,
  })

  const createEmptyPromptForm = () => ({
    name: '',
    content: '',
    description: '',
    source: '',
    enabled: true,
  })

  const createEmptySubagentForm = () => ({
    name: '',
    model: '',
    selectedToolNamesText: '',
    description: '',
    customSystemPrompt: '',
    systemPromptFilename: '',
    enabled: true,
    configText: '{}',
  })

  const [skillForm, setSkillForm] = useState(createEmptySkillForm)
  const [promptForm, setPromptForm] = useState(createEmptyPromptForm)
  const [subagentForm, setSubagentForm] = useState(createEmptySubagentForm)

  const [editingSkillId, setEditingSkillId] = useState<string | null>(null)
  const [editingPromptId, setEditingPromptId] = useState<string | null>(null)
  const [editingSubagentId, setEditingSubagentId] = useState<string | null>(null)

  const title = useMemo(() => 'Config Center', [])

  const promptAuthForConfigAction = (action: string) => {
    setSuccessMessage('')
    setErrorMessage(`请先登录后再${action}。`)
    requestAuthDialog('config-center')
  }

  const loadAll = async () => {
    if (!currentUserId) {
      setLlmConfigs([])
      setSkills([])
      setPrompts([])
      setSubagents([])
      return
    }

    setLoading(true)
    setErrorMessage('')
    try {
      const [llms, skillList, promptList, subagentList] = await Promise.all([
        listLlmConfigs(currentUserId),
        listSkills(currentUserId),
        listPrompts(currentUserId),
        listSubAgentConfigs(currentUserId),
      ])
      setLlmConfigs(llms)
      setSkills(skillList)
      setPrompts(promptList)
      setSubagents(subagentList)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '加载配置中心数据失败。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadAll()
  }, [currentUserId])

  const handleCreateLlm = async () => {
    if (!currentUserId) {
      promptAuthForConfigAction('创建 LLM 配置')
      return
    }

    setLoading(true)
    setErrorMessage('')
    setSuccessMessage('')
    try {
      await createLlmConfig({
        userId: currentUserId,
        usageId: llmForm.usageId,
        model: llmForm.model,
        apiKey: llmForm.apiKey,
        baseUrl: llmForm.baseUrl || undefined,
      })
      setSuccessMessage('LLM 配置创建成功。')
      setLlmForm({ usageId: '', model: '', apiKey: '', baseUrl: '' })
      await loadAll()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '创建 LLM 配置失败。')
    } finally {
      setLoading(false)
    }
  }

  const handleCreateSkill = async () => {
    if (!currentUserId) {
      promptAuthForConfigAction(editingSkillId ? '保存 Skill 修改' : '创建 Skill')
      return
    }

    setLoading(true)
    setErrorMessage('')
    setSuccessMessage('')
    try {
      const payload = {
        userId: currentUserId,
        name: skillForm.name,
        content: skillForm.content,
        description: skillForm.description || undefined,
        source: skillForm.source || undefined,
        enabled: skillForm.enabled,
      }

      if (editingSkillId) {
        await updateSkill(editingSkillId, payload)
        setSuccessMessage('技能更新成功。')
      } else {
        await createSkill(payload)
        setSuccessMessage('技能创建成功。')
      }

      setSkillForm(createEmptySkillForm())
      setEditingSkillId(null)
      await loadAll()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : `${editingSkillId ? '更新' : '创建'}技能失败。`)
    } finally {
      setLoading(false)
    }
  }

  const handleEditSkill = (item: SkillProfileSummary) => {
    if (!currentUserId) {
      promptAuthForConfigAction(`编辑 Skill ${item.name}`)
      return
    }

    setEditingSkillId(item.id)
    setErrorMessage('')
    setSuccessMessage('')
    setSkillForm({
      name: item.name,
      content: item.content,
      description: item.description ?? '',
      source: item.source ?? '',
      enabled: item.enabled,
    })
  }

  const handleToggleSkill = async (item: SkillProfileSummary) => {
    if (!currentUserId) {
      promptAuthForConfigAction(`${item.enabled ? '关闭' : '启用'} Skill ${item.name}`)
      return
    }

    setLoading(true)
    setErrorMessage('')
    setSuccessMessage('')
    try {
      await updateSkill(item.id, {
        userId: currentUserId,
        name: item.name,
        content: item.content,
        description: item.description ?? undefined,
        source: item.source ?? undefined,
        enabled: !item.enabled,
      })
      setSuccessMessage(`技能已${item.enabled ? '关闭' : '启用'}。`)
      if (editingSkillId === item.id) {
        setSkillForm((prev) => ({ ...prev, enabled: !item.enabled }))
      }
      await loadAll()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '切换技能启用状态失败。')
    } finally {
      setLoading(false)
    }
  }

  const handleCancelSkillEdit = () => {
    setEditingSkillId(null)
    setSkillForm(createEmptySkillForm())
    setErrorMessage('')
    setSuccessMessage('')
  }

  const handleCreatePrompt = async () => {
    if (!currentUserId) {
      promptAuthForConfigAction(editingPromptId ? '保存 Prompt 修改' : '创建 Prompt')
      return
    }

    setLoading(true)
    setErrorMessage('')
    setSuccessMessage('')
    try {
      const payload = {
        userId: currentUserId,
        name: promptForm.name,
        content: promptForm.content,
        description: promptForm.description || undefined,
        source: promptForm.source || undefined,
        enabled: promptForm.enabled,
      }

      if (editingPromptId) {
        await updatePrompt(editingPromptId, payload)
        setSuccessMessage('提示词更新成功。')
      } else {
        await createPrompt(payload)
        setSuccessMessage('提示词创建成功。')
      }

      setPromptForm(createEmptyPromptForm())
      setEditingPromptId(null)
      await loadAll()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : `${editingPromptId ? '更新' : '创建'}提示词失败。`)
    } finally {
      setLoading(false)
    }
  }

  const handleEditPrompt = (item: PromptConfigSummary) => {
    if (!currentUserId) {
      promptAuthForConfigAction(`编辑 Prompt ${item.name}`)
      return
    }

    setEditingPromptId(item.id)
    setErrorMessage('')
    setSuccessMessage('')
    setPromptForm({
      name: item.name,
      content: item.content,
      description: item.description ?? '',
      source: item.source ?? '',
      enabled: item.enabled,
    })
  }

  const handleTogglePrompt = async (item: PromptConfigSummary) => {
    if (!currentUserId) {
      promptAuthForConfigAction(`${item.enabled ? '关闭' : '启用'} Prompt ${item.name}`)
      return
    }

    setLoading(true)
    setErrorMessage('')
    setSuccessMessage('')
    try {
      await updatePrompt(item.id, {
        userId: currentUserId,
        name: item.name,
        content: item.content,
        description: item.description ?? undefined,
        source: item.source ?? undefined,
        enabled: !item.enabled,
      })
      setSuccessMessage(`提示词已${item.enabled ? '关闭' : '启用'}。`)
      if (editingPromptId === item.id) {
        setPromptForm((prev) => ({ ...prev, enabled: !item.enabled }))
      }
      await loadAll()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '切换提示词启用状态失败。')
    } finally {
      setLoading(false)
    }
  }

  const handleCancelPromptEdit = () => {
    setEditingPromptId(null)
    setPromptForm(createEmptyPromptForm())
    setErrorMessage('')
    setSuccessMessage('')
  }

  const handleCreateSubagent = async () => {
    if (!currentUserId) {
      promptAuthForConfigAction(editingSubagentId ? '保存子 Agent 修改' : '创建子 Agent')
      return
    }

    setLoading(true)
    setErrorMessage('')
    setSuccessMessage('')
    try {
      const selectedToolNames = subagentForm.selectedToolNamesText
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)

      const payload = {
        userId: currentUserId,
        name: subagentForm.name,
        model: subagentForm.model || undefined,
        selectedToolNames,
        description: subagentForm.description || undefined,
        customSystemPrompt: subagentForm.customSystemPrompt || undefined,
        systemPromptFilename: subagentForm.systemPromptFilename || undefined,
        enabled: subagentForm.enabled,
        config: JSON.parse(subagentForm.configText) as Record<string, unknown>,
      }

      if (editingSubagentId) {
        await updateSubAgentConfig(editingSubagentId, payload)
        setSuccessMessage('子 Agent 配置更新成功。')
      } else {
        await createSubAgentConfig(payload)
        setSuccessMessage('子 Agent 配置创建成功。')
      }

      setSubagentForm(createEmptySubagentForm())
      setEditingSubagentId(null)
      await loadAll()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : `${editingSubagentId ? '更新' : '创建'}子 Agent 配置失败。`)
    } finally {
      setLoading(false)
    }
  }

  const handleEditSubagent = (item: SubAgentConfigSummary) => {
    if (!currentUserId) {
      promptAuthForConfigAction(`编辑子 Agent ${item.name}`)
      return
    }

    setEditingSubagentId(item.id)
    setErrorMessage('')
    setSuccessMessage('')
    setSubagentForm({
      name: item.name,
      model: item.model ?? '',
      selectedToolNamesText: (item.selected_tool_names ?? []).join(', '),
      description: item.description ?? '',
      customSystemPrompt: item.custom_system_prompt ?? '',
      systemPromptFilename: item.system_prompt_filename ?? '',
      enabled: item.enabled,
      configText: JSON.stringify(item.config ?? {}, null, 2),
    })
  }

  const handleToggleSubagent = async (item: SubAgentConfigSummary) => {
    if (!currentUserId) {
      promptAuthForConfigAction(`${item.enabled ? '关闭' : '启用'}子 Agent ${item.name}`)
      return
    }

    setLoading(true)
    setErrorMessage('')
    setSuccessMessage('')
    try {
      await updateSubAgentConfig(item.id, {
        userId: currentUserId,
        name: item.name,
        model: item.model ?? undefined,
        selectedToolNames: item.selected_tool_names ?? [],
        description: item.description ?? undefined,
        customSystemPrompt: item.custom_system_prompt ?? undefined,
        systemPromptFilename: item.system_prompt_filename ?? undefined,
        enabled: !item.enabled,
        config: item.config ?? {},
      })
      setSuccessMessage(`子 Agent 已${item.enabled ? '关闭' : '启用'}。`)
      if (editingSubagentId === item.id) {
        setSubagentForm((prev) => ({ ...prev, enabled: !item.enabled }))
      }
      await loadAll()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '切换子 Agent 启用状态失败。')
    } finally {
      setLoading(false)
    }
  }

  const handleCancelSubagentEdit = () => {
    setEditingSubagentId(null)
    setSubagentForm(createEmptySubagentForm())
    setErrorMessage('')
    setSuccessMessage('')
  }

  return (
    <div className="workspace-shell">
      <div className="aurora aurora-one" />
      <div className="aurora aurora-two" />
      <header className="topbar">
        <div className="topbar-copy">
          <span className="eyebrow">Configuration</span>
          <h1>{title}</h1>
          <p>在前端直接管理 LLM、技能、提示词与子 Agent 配置。</p>
        </div>
      </header>
      <main className="workspace-page-body config-center-page-body">
        <section className="panel panel-feature config-center-shell">
          <div className="section-heading">
            <div>
              <h2>配置资源</h2>
              <span className="section-note">运行时组合资源中心</span>
            </div>
            <div className="config-center-actions">
              <button type="button" className="ghost-button" onClick={() => void loadAll()} disabled={loading}>
                刷新
              </button>
            </div>
          </div>

          <div className="workspace-tab-list config-center-tabs">
            {(['llms', 'skills', 'prompts', 'subagents'] as ConfigTab[]).map((tab) => (
              <button
                key={tab}
                type="button"
                className={`workspace-tab ${activeTab === tab ? 'active' : ''}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab === 'llms'
                  ? 'LLM Configs'
                  : tab === 'skills'
                    ? 'Skills'
                    : tab === 'prompts'
                      ? 'Prompts'
                      : 'SubAgents'}
              </button>
            ))}
          </div>

          {isGuest ? (
            <div className="config-center-banner guest">
              <span>当前为访客模式，可以先浏览配置结构。创建、编辑、启用等写操作会在点击时提示登录。</span>
              <button
                type="button"
                className="ghost-button config-center-banner__action"
                onClick={() => requestAuthDialog('config-center')}
              >
                立即登录
              </button>
            </div>
          ) : null}

          {errorMessage ? <div className="config-center-banner error">{errorMessage}</div> : null}
          {successMessage ? <div className="config-center-banner success">{successMessage}</div> : null}

          {activeTab === 'llms' ? (
            <div className="config-center-grid">
              <section className="panel config-form-panel">
                <div className="section-heading"><h2>新建 LLM 配置</h2></div>
                <div className="config-form-grid">
                  <input placeholder="usage_id" value={llmForm.usageId} onChange={(e) => setLlmForm({ ...llmForm, usageId: e.target.value })} />
                  <input placeholder="model" value={llmForm.model} onChange={(e) => setLlmForm({ ...llmForm, model: e.target.value })} />
                  <input placeholder="api_key" value={llmForm.apiKey} onChange={(e) => setLlmForm({ ...llmForm, apiKey: e.target.value })} />
                  <input placeholder="base_url(optional)" value={llmForm.baseUrl} onChange={(e) => setLlmForm({ ...llmForm, baseUrl: e.target.value })} />
                </div>
                <button type="button" onClick={() => void handleCreateLlm()} disabled={loading}>创建</button>
              </section>
              <section className="panel config-list-panel">
                <div className="section-heading"><h2>LLM 列表</h2><span className="section-note">{llmConfigs.length} items</span></div>
                <div className="config-card-list">
                  {llmConfigs.map((item) => (
                    <article key={item.id} className="config-card">
                      <strong>{item.model}</strong>
                      <span>{item.id}</span>
                      <span>{item.usage_id}</span>
                    </article>
                  ))}
                </div>
              </section>
            </div>
          ) : null}

          {activeTab === 'skills' ? (
            <div className="config-center-grid">
              <section className="panel config-form-panel">
                <div className="section-heading">
                  <h2>{editingSkillId ? '编辑 Skill' : '新建 Skill'}</h2>
                  {editingSkillId ? (
                    <button type="button" className="ghost-button" onClick={handleCancelSkillEdit} disabled={loading}>
                      取消编辑
                    </button>
                  ) : null}
                </div>

                <div className="config-form-grid">
                  <input placeholder="name" value={skillForm.name} onChange={(e) => setSkillForm({ ...skillForm, name: e.target.value })} />
                  <input placeholder="source(optional)" value={skillForm.source} onChange={(e) => setSkillForm({ ...skillForm, source: e.target.value })} />
                  <input placeholder="description(optional)" value={skillForm.description} onChange={(e) => setSkillForm({ ...skillForm, description: e.target.value })} />
                  <label className="config-switch-row">
                    <span>是否启用</span>
                    <input type="checkbox" checked={skillForm.enabled} onChange={(e) => setSkillForm({ ...skillForm, enabled: e.target.checked })} />
                  </label>
                  <textarea placeholder="content" value={skillForm.content} onChange={(e) => setSkillForm({ ...skillForm, content: e.target.value })} />
                </div>

                <button type="button" onClick={() => void handleCreateSkill()} disabled={loading}>
                  {editingSkillId ? '保存修改' : '创建'}
                </button>
              </section>

              <section className="panel config-list-panel">
                <div className="section-heading"><h2>Skill 列表</h2><span className="section-note">{skills.length} items</span></div>
                <div className="config-card-list">
                  {skills.map((item) => (
                    <article
                      key={item.id}
                      className={`config-card config-card-interactive ${editingSkillId === item.id ? 'active' : ''}`}
                      onClick={() => handleEditSkill(item)}
                    >
                      <div className="config-card-header">
                        <div>
                          <strong>{item.name}</strong>
                          <span>{item.id}</span>
                        </div>
                        <button
                          type="button"
                          className={`config-toggle ${item.enabled ? 'is-enabled' : ''}`}
                          aria-label={`${item.enabled ? '关闭' : '启用'} ${item.name}`}
                          aria-pressed={item.enabled}
                          onClick={(event) => {
                            event.stopPropagation()
                            void handleToggleSkill(item)
                          }}
                        >
                          <span className="config-toggle-thumb" />
                        </button>
                      </div>
                      <span>{item.enabled ? '已启用' : '未启用'}</span>
                      <p>{item.description || item.source || '无补充说明'}</p>
                    </article>
                  ))}
                </div>
              </section>
            </div>
          ) : null}

          {activeTab === 'prompts' ? (
            <div className="config-center-grid">
              <section className="panel config-form-panel">
                <div className="section-heading">
                  <h2>{editingPromptId ? '编辑 Prompt' : '新建 Prompt'}</h2>
                  {editingPromptId ? (
                    <button type="button" className="ghost-button" onClick={handleCancelPromptEdit} disabled={loading}>
                      取消编辑
                    </button>
                  ) : null}
                </div>

                <div className="config-form-grid">
                  <input placeholder="name" value={promptForm.name} onChange={(e) => setPromptForm({ ...promptForm, name: e.target.value })} />
                  <input placeholder="source(optional)" value={promptForm.source} onChange={(e) => setPromptForm({ ...promptForm, source: e.target.value })} />
                  <input placeholder="description(optional)" value={promptForm.description} onChange={(e) => setPromptForm({ ...promptForm, description: e.target.value })} />
                  <label className="config-switch-row">
                    <span>是否启用</span>
                    <input type="checkbox" checked={promptForm.enabled} onChange={(e) => setPromptForm({ ...promptForm, enabled: e.target.checked })} />
                  </label>
                  <textarea placeholder="content" value={promptForm.content} onChange={(e) => setPromptForm({ ...promptForm, content: e.target.value })} />
                </div>

                <button type="button" onClick={() => void handleCreatePrompt()} disabled={loading}>
                  {editingPromptId ? '保存修改' : '创建'}
                </button>
              </section>

              <section className="panel config-list-panel">
                <div className="section-heading"><h2>Prompt 列表</h2><span className="section-note">{prompts.length} items</span></div>
                <div className="config-card-list">
                  {prompts.map((item) => (
                    <article
                      key={item.id}
                      className={`config-card config-card-interactive ${editingPromptId === item.id ? 'active' : ''}`}
                      onClick={() => handleEditPrompt(item)}
                    >
                      <div className="config-card-header">
                        <div>
                          <strong>{item.name}</strong>
                          <span>{item.id}</span>
                        </div>
                        <button
                          type="button"
                          className={`config-toggle ${item.enabled ? 'is-enabled' : ''}`}
                          aria-label={`${item.enabled ? '关闭' : '启用'} ${item.name}`}
                          aria-pressed={item.enabled}
                          onClick={(event) => {
                            event.stopPropagation()
                            void handleTogglePrompt(item)
                          }}
                        >
                          <span className="config-toggle-thumb" />
                        </button>
                      </div>
                      <span>{item.enabled ? '已启用' : '未启用'}</span>
                      <p>{item.description || item.source || '无补充说明'}</p>
                    </article>
                  ))}
                </div>
              </section>
            </div>
          ) : null}

          {activeTab === 'subagents' ? (
            <div className="config-center-grid">
              <section className="panel config-form-panel">
                <div className="section-heading">
                  <h2>{editingSubagentId ? '编辑 SubAgent Config' : '新建 SubAgent Config'}</h2>
                  {editingSubagentId ? (
                    <button type="button" className="ghost-button" onClick={handleCancelSubagentEdit} disabled={loading}>
                      取消编辑
                    </button>
                  ) : null}
                </div>

                <div className="config-form-grid">
                  <input placeholder="name" value={subagentForm.name} onChange={(e) => setSubagentForm({ ...subagentForm, name: e.target.value })} />
                  <input placeholder="model(optional)" value={subagentForm.model} onChange={(e) => setSubagentForm({ ...subagentForm, model: e.target.value })} />
                  <input placeholder="tools (comma separated)" value={subagentForm.selectedToolNamesText} onChange={(e) => setSubagentForm({ ...subagentForm, selectedToolNamesText: e.target.value })} />
                  <input placeholder="description(optional)" value={subagentForm.description} onChange={(e) => setSubagentForm({ ...subagentForm, description: e.target.value })} />
                  <input placeholder="system_prompt_filename(optional)" value={subagentForm.systemPromptFilename} onChange={(e) => setSubagentForm({ ...subagentForm, systemPromptFilename: e.target.value })} />
                  <textarea placeholder="custom_system_prompt(optional)" value={subagentForm.customSystemPrompt} onChange={(e) => setSubagentForm({ ...subagentForm, customSystemPrompt: e.target.value })} />
                  <label className="config-switch-row">
                    <span>是否启用</span>
                    <input type="checkbox" checked={subagentForm.enabled} onChange={(e) => setSubagentForm({ ...subagentForm, enabled: e.target.checked })} />
                  </label>
                  <textarea placeholder="config (JSON)" value={subagentForm.configText} onChange={(e) => setSubagentForm({ ...subagentForm, configText: e.target.value })} />
                </div>

                <button type="button" onClick={() => void handleCreateSubagent()} disabled={loading}>
                  {editingSubagentId ? '保存修改' : '创建'}
                </button>
              </section>

              <section className="panel config-list-panel">
                <div className="section-heading"><h2>SubAgent 列表</h2><span className="section-note">{subagents.length} items</span></div>
                <div className="config-card-list">
                  {subagents.map((item) => (
                    <article
                      key={item.id}
                      className={`config-card config-card-interactive ${editingSubagentId === item.id ? 'active' : ''}`}
                      onClick={() => handleEditSubagent(item)}
                    >
                      <div className="config-card-header">
                        <div>
                          <strong>{item.name}</strong>
                          <span>{item.id}</span>
                        </div>
                        <button
                          type="button"
                          className={`config-toggle ${item.enabled ? 'is-enabled' : ''}`}
                          aria-label={`${item.enabled ? '关闭' : '启用'} ${item.name}`}
                          aria-pressed={item.enabled}
                          onClick={(event) => {
                            event.stopPropagation()
                            void handleToggleSubagent(item)
                          }}
                        >
                          <span className="config-toggle-thumb" />
                        </button>
                      </div>
                      <span>{item.enabled ? '已启用' : '未启用'}</span>
                      <p>{item.description || item.model || '无补充说明'}</p>
                    </article>
                  ))}
                </div>
              </section>
            </div>
          ) : null}
        </section>
      </main>
    </div>
  )
}
