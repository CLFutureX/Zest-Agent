import { MetaBlock } from './MetaBlock'



type ConversationSidebarProps = {

  conversationText: string

  accessText: string

}



export function ConversationSidebar({ conversationText, accessText }: ConversationSidebarProps) {

  return (

    <aside className="chat-sidebar panel panel-feature">

      <div className="section-heading">

        <h2>当前上下文</h2>

        <span className="section-note">Conversation state</span>

      </div>

      <MetaBlock label="Conversation" value={conversationText} />

      <MetaBlock label="Runtime Access" value={accessText} />

    </aside>

  )

}
