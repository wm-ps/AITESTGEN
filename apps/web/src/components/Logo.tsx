export function Logo({ size = 34 }: { size?: number }) {
  const s = size / 34
  const px = (n: number) => Math.round(n * s)

  return (
    <div
      aria-hidden="true"
      style={{
        width: size,
        height: size,
        borderRadius: px(10),
        background: 'linear-gradient(135deg, var(--signal) 0%, var(--signal) 65%, rgba(0,0,0,0.22) 100%)',
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.4), inset 0 -6px 10px rgba(0,0,0,0.15)',
        position: 'relative',
        flexShrink: 0,
        overflow: 'hidden',
      }}
    >
      <span style={{ position: 'absolute', width: 4, height: 4, borderRadius: 'var(--radius-full)', background: 'rgba(255,255,255,0.6)', top: px(6), left: px(15) }} />
      <span style={{ position: 'absolute', width: 4, height: 4, borderRadius: 'var(--radius-full)', background: 'rgba(255,255,255,0.6)', top: px(22), left: px(6) }} />
      <span style={{ position: 'absolute', width: 4, height: 4, borderRadius: 'var(--radius-full)', background: 'rgba(255,255,255,0.6)', top: px(22), left: px(23) }} />
      <span style={{ position: 'absolute', width: px(15), height: 1, background: 'rgba(255,255,255,0.4)', top: px(12), left: px(8), transform: 'rotate(53deg)', transformOrigin: 'left center' }} />
      <span style={{ position: 'absolute', width: px(15), height: 1, background: 'rgba(255,255,255,0.4)', top: px(12), left: px(16), transform: 'rotate(-53deg)', transformOrigin: 'left center' }} />
      <span style={{ position: 'absolute', width: px(15), height: 1, background: 'rgba(255,255,255,0.4)', top: px(23), left: px(8) }} />
      <span
        style={{
          position: 'absolute',
          width: 5,
          height: 5,
          borderRadius: 'var(--radius-full)',
          background: '#ffffff',
          boxShadow: '0 0 5px rgba(255,255,255,0.95)',
          animation: 'aitg-path-travel 3.6s ease-in-out infinite',
        }}
      />
    </div>
  )
}
