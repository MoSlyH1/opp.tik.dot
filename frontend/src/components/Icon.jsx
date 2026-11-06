const PATHS = {
  home: 'M3 10.5 12 3l9 7.5V21h-6v-6H9v6H3z',
  search: 'M10.5 3a7.5 7.5 0 1 1 0 15 7.5 7.5 0 0 1 0-15zm0 2a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11zM15.6 17l1.4-1.4 4.4 4.4-1.4 1.4z',
  user: 'M12 3a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9zM4 20.5C4 16.4 7.6 14 12 14s8 2.4 8 6.5V21H4z',
  heart: 'M12 20.5 4.2 12.8a4.9 4.9 0 0 1 7-7l.8.8.8-.8a4.9 4.9 0 0 1 7 7z',
  bookmark: 'M6 3h12v18l-6-4.5L6 21z',
  share: 'M14 4l7 7-7 7v-4.2c-5 0-8.2 1.6-11 5.2 1-5.4 4-10.6 11-11.6z',
  external: 'M14 3h7v7h-2V6.4l-8.3 8.3-1.4-1.4L17.6 5H14zM5 5h6v2H7v10h10v-4h2v6H5z',
  eyeOff: 'M3.3 2 22 20.7 20.7 22l-3.4-3.4A11 11 0 0 1 1 12a11.3 11.3 0 0 1 4.3-5.3L2 3.3zM12 5c5.2 0 9.4 3.4 11 7a11.6 11.6 0 0 1-3 4.1L7.8 3.9A11 11 0 0 1 12 5z',
  volume: 'M4 9h4l5-4v14l-5-4H4zm12.5-.6a5 5 0 0 1 0 7.2l-1.4-1.4a3 3 0 0 0 0-4.4zm2.8-2.8a9 9 0 0 1 0 12.8l-1.4-1.4a7 7 0 0 0 0-10z',
  mute: 'M4 9h4l5-4v14l-5-4H4zm11.3.7 1.4-1.4 2.3 2.3 2.3-2.3 1.4 1.4-2.3 2.3 2.3 2.3-1.4 1.4-2.3-2.3-2.3 2.3-1.4-1.4 2.3-2.3z',
  up: 'M12 7l7 7-1.4 1.4L12 9.8l-5.6 5.6L5 14z',
  down: 'M12 17l-7-7 1.4-1.4 5.6 5.6 5.6-5.6L19 10z',
  back: 'M15 5l1.4 1.4L10.8 12l5.6 5.6L15 19l-7-7z',
  rewind: 'M12 4a8 8 0 1 1-7.4 11h2.2A6 6 0 1 0 6.4 8.6L9 11H3V5l2 2A8 8 0 0 1 12 4zm-1 4h2v4.2l3 1.8-1 1.7-4-2.4z',
}

export default function Icon({ name, size = 22, filled = true, ...rest }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true"
      fill={filled ? 'currentColor' : 'none'} stroke={filled ? 'none' : 'currentColor'}
      strokeWidth={filled ? 0 : 1.8} strokeLinejoin="round" {...rest}>
      <path d={PATHS[name]} />
    </svg>
  )
}
