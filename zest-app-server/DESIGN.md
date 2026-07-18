五、服务注册与发现
期望： AgentServer定期上报自己的信息，AppServer收集信息并定期检查心跳是否存活；
      基于负载均衡策略从健康实例中选择一个AgentServer作为被调度方完成任务调度；
设计上：
1 AgentServer作为Client端，主要有上报和注销；
AgentRegistryClient
2 AppServer 作为Server端，主要会通过watch_loop定时拉取或监听变更，更新本地的AgentServer集合缓存，并向上提供获取接口。
