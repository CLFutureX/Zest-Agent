type WorkspaceArtifactPanelProps = {

  artifacts: string[]

}



type ArtifactKind = 'image' | 'markdown' | 'code' | 'file'



const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'])

const MARKDOWN_EXTENSIONS = new Set(['md', 'mdx'])

const CODE_EXTENSIONS = new Set([

  'ts',

  'tsx',

  'js',

  'jsx',

  'json',

  'py',

  'java',

  'go',

  'rs',

  'css',

  'html',

  'yml',

  'yaml',

  'sh',

  'sql',

])



function getExt(filePath: string): string {

  return filePath.split('.').pop()?.toLowerCase() ?? ''

}



function getArtifactKind(filePath: string): ArtifactKind {

  const ext = getExt(filePath)

  if (IMAGE_EXTENSIONS.has(ext)) return 'image'

  if (MARKDOWN_EXTENSIONS.has(ext)) return 'markdown'

  if (CODE_EXTENSIONS.has(ext)) return 'code'

  return 'file'

}



function getTypeLabel(filePath: string): string {

  const ext = getExt(filePath)

  if (!ext) return 'FILE'

  return ext.toUpperCase()

}



function getFileName(filePath: string): string {

  return filePath.split(/[\\/]/).pop() ?? filePath

}



function getArtifactIcon(kind: ArtifactKind): string {

  switch (kind) {

    case 'image':

      return '🖼️'

    case 'markdown':

      return '📝'

    case 'code':

      return '⌘'

    default:

      return '📄'

  }

}



function getArtifactHint(kind: ArtifactKind): string {

  switch (kind) {

    case 'image':

      return '可预览图片资源'

    case 'markdown':

      return '文档型产物'

    case 'code':

      return '代码或结构化文件'

    default:

      return '通用附件文件'

  }

}



export function WorkspaceArtifactPanel({ artifacts }: WorkspaceArtifactPanelProps) {

  if (artifacts.length === 0) {

    return <div className="workspace-artifact-panel__empty">暂无资源文件</div>

  }



  return (

    <div className="workspace-artifact-panel__list">

      {artifacts.map((filePath) => {

        const kind = getArtifactKind(filePath)

        const fileName = getFileName(filePath)



        return (

          <article key={filePath} className={`workspace-artifact-card workspace-artifact-card--${kind}`}>

            {kind === 'image' && (

              <div className="workspace-artifact-card__preview">

                <img className="workspace-artifact-card__image" src={filePath} alt={fileName} />

              </div>

            )}

            <button

              type="button"

              className="workspace-artifact-card__main"

              onClick={() => window.open(filePath, '_blank', 'noopener,noreferrer')}

            >

              <span className="workspace-artifact-card__icon">{getArtifactIcon(kind)}</span>

              <span className="workspace-artifact-card__body">

                <span className="workspace-artifact-card__name" title={filePath}>

                  {fileName}

                </span>

                <span className="workspace-artifact-card__meta">{getTypeLabel(filePath)} file</span>

                <span className="workspace-artifact-card__hint">{getArtifactHint(kind)}</span>

              </span>

            </button>

            <a

              className="workspace-artifact-card__download"

              href={filePath}

              download={fileName}

              target="_blank"

              rel="noreferrer"

              title="下载"

            >

              下载

            </a>

          </article>

        )

      })}

    </div>

  )

}
