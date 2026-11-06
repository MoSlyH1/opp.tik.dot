// A watch whose hands tick counter-clockwise: time running backwards.
export default function Logo({ size = 32, animate = true, title = 'opp.tik.dot' }) {
  const ticks = Array.from({ length: 12 }, (_, i) => {
    const a = (i * Math.PI) / 6
    const major = i % 3 === 0
    const r1 = major ? 19 : 21
    return (
      <line key={i}
        x1={32 + Math.sin(a) * r1} y1={32 - Math.cos(a) * r1}
        x2={32 + Math.sin(a) * 24} y2={32 - Math.cos(a) * 24}
        strokeWidth={major ? 3 : 1.6} />
    )
  })
  return (
    <svg className={`logo ${animate ? 'logo--animate' : ''}`} viewBox="0 0 64 64"
      width={size} height={size} role="img" aria-label={title}>
      <circle cx="32" cy="32" r="29" fill="#fff" stroke="#000" strokeWidth="3" />
      <circle cx="32" cy="32" r="26.5" fill="none" stroke="#000" strokeWidth="1" />
      <g stroke="#000" strokeLinecap="round">{ticks}</g>
      <g className="logo__min"><line x1="32" y1="32" x2="32" y2="15" stroke="#000" strokeWidth="3.4" strokeLinecap="round" /></g>
      <g className="logo__sec"><line x1="32" y1="36" x2="32" y2="11" stroke="#000" strokeWidth="1.4" strokeLinecap="round" /></g>
      <circle cx="32" cy="32" r="2.8" fill="#000" />
    </svg>
  )
}
