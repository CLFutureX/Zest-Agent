type AlertBannerProps = {
  message: string
  onClose: () => void
}

export function AlertBanner({ message, onClose }: AlertBannerProps) {
  return (
    <div className="alert-banner" role="alert">
      <span>{message}</span>
      <button type="button" className="ghost-button" onClick={onClose}>
        关闭
      </button>
    </div>
  )
}
