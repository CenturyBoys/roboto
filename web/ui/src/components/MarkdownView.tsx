import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Mermaid } from './Mermaid'

// Renderiza markdown (GFM: tabelas, checklists, links) + diagramas ```mermaid. Usado no preview do
// DoR/proposta (IssueRefine) e reutilizável. Bloco ```mermaid vira diagrama; demais code = <pre>.
export function MarkdownView({ children }: { children: string }) {
  return (
    <Markdown
      remarkPlugins={[remarkGfm]}
      components={{
        code({ className, children, ...props }) {
          if (/\blanguage-mermaid\b/.test(className || '')) {
            return <Mermaid chart={String(children)} />
          }
          return (
            <code className={className} {...props}>
              {children}
            </code>
          )
        },
      }}
    >
      {children}
    </Markdown>
  )
}
