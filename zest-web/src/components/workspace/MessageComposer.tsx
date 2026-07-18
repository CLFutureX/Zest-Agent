import { useEffect, useState } from 'react'

type LlmConfigOption = {
  value: string
  label: string
}

type MessageComposerProps = {
  busy: boolean
  defaultModel?: string
  defaultLlmConfigId?: string
  llmConfigOptions?: LlmConfigOption[]
  welcomeMode?: boolean
  onSubmit: (input: { content: string; model?: string; llmConfigId?: string }) => Promise<void>
}

export function MessageComposer({
  busy,
  defaultModel = '',
  defaultLlmConfigId = '',
  llmConfigOptions = [],
  welcomeMode = false,
  onSubmit,
}: MessageComposerProps) {
  const [message, setMessage] = useState('')
  const [model, setModel] = useState(defaultModel)
  const [llmConfigId, setLlmConfigId] = useState(defaultLlmConfigId)

  useEffect(() => {
    setModel(defaultModel)
  }, [defaultModel])

  useEffect(() => {
    setLlmConfigId(defaultLlmConfigId)
  }, [defaultLlmConfigId])

  const handleSubmit = async () => {
    const content = message.trim()
    if (!content) return

    await onSubmit({
      content,
      model: model.trim() || undefined, 
    })

    setMessage('')
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void handleSubmit()
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setMessage(e.target.value)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }

  return (
    <div className={`df-composer${welcomeMode ? ' df-composer--welcome' : ''}`}>
      <div className="df-composer-inner">
        <textarea
          className="df-composer-textarea"
          value={message}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={welcomeMode ? '输入你的目标，我会创建会话并开始执行…' : '给当前会话发送消息…'}
          rows={1}
          disabled={busy}
        />
        <div className="df-composer-footer">
          <div className="df-composer-meta">
            {llmConfigOptions.length > 0 && (
              <select
                className="df-composer-select"
                value={llmConfigId}
                onChange={(e) => setLlmConfigId(e.target.value)}
                disabled={busy}
              >
                <option value="">default</option>
                {llmConfigOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            )}
          </div>
          <button
            type="button"
            className="df-composer-send"
            disabled={busy || !message.trim()}
            onClick={() => { void handleSubmit() }}
          >
            {busy ? '…' : '↑'}
          </button>
        </div>
      </div>
    </div>
  )
}
