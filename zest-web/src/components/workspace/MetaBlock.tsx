type MetaBlockProps = {
  label: string
  value: string
}

export function MetaBlock({ label, value }: MetaBlockProps) {
  return (
    <div className="meta-item">
      <span className="meta-label">{label}</span>
      <pre className="meta-value">{value}</pre>
    </div>
  )
}
