import vantageMark from '../assets/vantage-mark.png'

export function Logo({ size = 34 }: { size?: number }) {
  return <img src={vantageMark} alt="" aria-hidden="true" width={size} style={{ height: 'auto', display: 'block', flexShrink: 0 }} />
}
