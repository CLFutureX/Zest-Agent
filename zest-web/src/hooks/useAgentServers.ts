import { useCallback, useEffect, useState } from 'react'



import { listAgentServers } from '../services/appServerApi'



import type { AgentServerSummary } from '../types/workspace'



export function useAgentServers() {



  const [servers, setServers] = useState<AgentServerSummary[]>([])



  const [loading, setLoading] = useState(false)



  const [errorMessage, setErrorMessage] = useState('')



  const [statusFilter, setStatusFilter] = useState<string>('')



  const refresh = useCallback(async (status = statusFilter) => {



    setLoading(true)



    setErrorMessage('')



    try {



      const data = await listAgentServers(status || undefined)



      setServers(data.servers)



    } catch (error) {



      setErrorMessage(error instanceof Error ? error.message : '获取 AgentServer 列表失败。')



    } finally {



      setLoading(false)



    }



  }, [statusFilter])



  useEffect(() => {



    void refresh(statusFilter)



  }, [refresh, statusFilter])



  return { servers, loading, errorMessage, refresh, statusFilter, setStatusFilter }



}
