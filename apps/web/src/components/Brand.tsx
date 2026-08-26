import vantageLogo from '../assets/vantage-logo-v2.png'

export function VantageBrand({ markSize = 44 }: { markSize?: number }) {
  return <img src={vantageLogo} alt="Vantage" height={markSize} style={{ width: 'auto', display: 'block' }} />
}
