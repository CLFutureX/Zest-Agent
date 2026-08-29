import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/**
 * 记忆设置（用户级偏好，持久化到 localStorage）。
 *
 * 这两个开关作用于「后续新建会话」：
 * - enable_base_memory       是否启用基础记忆（profile / preferences / domain / project）
 * - enable_experience_memory  是否启用经验记忆（向量检索 + 写入）
 *
 * 默认均为 true（与后端 ConversationCreatePayload 默认一致）。
 * 新建会话时由 useWorkspaceRuntime.handleOpenConversation 透传到后端。
 */
export type MemorySettings = {
  enable_base_memory: boolean
  enable_experience_memory: boolean
}

type MemorySettingsState = MemorySettings & {
  setMemorySettings: (patch: Partial<MemorySettings>) => void
  setEnableBaseMemory: (enabled: boolean) => void
  setEnableExperienceMemory: (enabled: boolean) => void
}

export const useMemorySettingsStore = create<MemorySettingsState>()(
  persist(
    (set) => ({
      enable_base_memory: true,
      enable_experience_memory: true,
      setMemorySettings: (patch) => set((state) => ({ ...state, ...patch })),
      setEnableBaseMemory: (enabled) => set({ enable_base_memory: enabled }),
      setEnableExperienceMemory: (enabled) => set({ enable_experience_memory: enabled }),
    }),
    {
      name: 'zest-memory-settings',
      // 仅持久化数据字段，不持久化 action
      partialize: (state) => ({
        enable_base_memory: state.enable_base_memory,
        enable_experience_memory: state.enable_experience_memory,
      }),
    },
  ),
)
