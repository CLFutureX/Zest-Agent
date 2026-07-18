import type { FormEvent } from 'react'



type SessionPanelProps = {



  busy: boolean



  onSubmit: (input: { title: string; initialMessage?: string; workspace?: string; model?: string }) => Promise<void>



}







export function SessionPanel({ busy, onSubmit }: SessionPanelProps) {



  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {



    event.preventDefault()



    const form = new FormData(event.currentTarget)



    await onSubmit({







      title: String(form.get('title') || '新会话').trim() || '新会话',







      initialMessage: String(form.get('initialMessage') || ''),







      workspace: String(form.get('workspace') || ''),







      model: String(form.get('model') || ''),







    })



  }







  return (



    <section className="panel workspace-form-panel panel-feature">



      <div className="section-heading">



        <h2>打开会话</h2>



        <span className="section-note">Conversation boot</span>



      </div>







      <form onSubmit={handleSubmit}>



        <input name="title" placeholder="会话标题" defaultValue="新的 Agent 会话" />



        <input name="model" placeholder="model (optional)" />



        <input name="workspace" placeholder="workspace (optional)" />



        <textarea name="initialMessage" placeholder="可选：直接输入首条消息，留空也可先进入会话" />



        <button type="submit" disabled={busy}>打开会话</button>



      </form>



    </section>



  )



}
