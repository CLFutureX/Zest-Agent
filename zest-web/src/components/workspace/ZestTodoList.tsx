import { useState } from 'react'
import type { TodoItem } from '../../types/workspace'

type Props = {
  todos: TodoItem[]
  className?: string
  inline?: boolean
}

const STATUS_LABEL: Record<string, string> = {
  pending: 'Pending',
  in_progress: 'In Progress',
  completed: 'Done',
  cancelled: 'Cancelled',
}

export function ZestTodoList({ todos, className, inline = false }: Props) {
  const [collapsed, setCollapsed] = useState(false)

  if (todos.length === 0) return null

  const doneCount = todos.filter((t) => t.status === 'completed').length

  return (
    <div className={`zest-todo-list${inline ? ' zest-todo-list--inline' : ''} ${className ?? ''}`.trim()}>
      <header className="zest-todo-header" onClick={() => setCollapsed((v) => !v)}>
        <span className="zest-todo-title">
          <span className="zest-todo-icon">☑</span>
          To-dos
        </span>
        <span className="zest-todo-count">{doneCount}/{todos.length} 已完成</span>
        <span className={`zest-todo-chevron${collapsed ? '' : ' open'}`}>›</span>
      </header>

      {!collapsed && (
        <ul className="zest-todo-items">
          {todos.map((todo, i) => (
            <li key={i} className={`zest-todo-item zest-todo-item--${todo.status}`}>
              <span className="zest-todo-indicator" />
              <span className="zest-todo-content">{todo.content}</span>
              <span className="zest-todo-status">{STATUS_LABEL[todo.status] ?? todo.status}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}