import type { FormEvent } from 'react'

type TaskPanelProps = {
  busy: boolean
  disabled: boolean
  onSubmit: (input: { title: string; description: string }) => Promise<void>
}
 
export function TaskPanel({ busy, disabled, onSubmit }: TaskPanelProps) {
  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    await onSubmit({
      title: String(form.get('taskTitle') || '未命名任务'),
      description: String(form.get('taskDescription') || ''),
    })
  }

  return (
    <section className="panel">
      <h2>2. 创建 Task 并启动 Agent</h2>
      <form onSubmit={handleSubmit}>
        <input name="taskTitle" placeholder="任务标题" />
        <textarea name="taskDescription" placeholder="任务描述" />
        <button type="submit" disabled={busy || disabled}>创建 Task</button>
      </form>
    </section>
  )
}
