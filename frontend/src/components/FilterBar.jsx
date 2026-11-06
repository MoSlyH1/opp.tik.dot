import Icon from './Icon.jsx'

export function ChipGroup({ options, value, onChange, allLabel }) {
  const toggle = (id) => onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id])
  return (
    <div className="chips" role="group">
      {allLabel && (
        <button type="button" className={`chip ${value.length === 0 ? 'on' : ''}`} onClick={() => onChange([])}>
          {allLabel}
        </button>
      )}
      {options.map((o) => (
        <button type="button" key={o.id} className={`chip ${value.includes(o.id) ? 'on' : ''}`}
          aria-pressed={value.includes(o.id)} onClick={() => toggle(o.id)}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

export default function FilterBar({ meta, value, onChange }) {
  const set = (patch) => onChange({ ...value, ...patch })
  return (
    <div className="filterbar">
      <div className="filter-row">
        <ChipGroup options={meta.eras || []} value={value.era} allLabel="All eras"
          onChange={(era) => set({ era })} />
        <button type="button" className={`chip rewind ${value.reverse ? 'on' : ''}`}
          aria-pressed={value.reverse} onClick={() => set({ reverse: !value.reverse })}
          title="Rewind mode: scroll in the opposite direction">
          <Icon name="rewind" size={16} /> {value.reverse ? 'Rewind on' : 'Rewind'}
        </button>
      </div>
      <div className="filter-row">
        <ChipGroup options={meta.categories || []} value={value.category} allLabel="Everything"
          onChange={(category) => set({ category })} />
      </div>
    </div>
  )
}
