import type { Comparison, PairedField, PairedRow } from './types';

const words = (value: string) => value.replaceAll('_', ' ').replaceAll('-', ' ');
const fixed = (value: number | null | undefined, digits = 2) => value === null || value === undefined ? '—' : value.toFixed(digits);
const field = (row: PairedRow, name: string) => row[name] as PairedField;

function Bars({ rows, metric, leftLabel, rightLabel, lowerIsBetter = true }: { rows: PairedRow[]; metric: string; leftLabel: string; rightLabel: string; lowerIsBetter?: boolean }) {
  const values = rows.flatMap(r => [field(r, metric).left, field(r, metric).right]).filter((v): v is number => v !== null);
  const max = Math.max(1e-9, ...values);
  return <div className="pair-bars">
    <div className="pair-legend"><span><i className="swatch left"/>{leftLabel}</span><span><i className="swatch right"/>{rightLabel}</span><span className="legend-note">{lowerIsBetter ? 'Lower is better' : 'Higher is better'}</span></div>
    {rows.map(r => { const f = field(r, metric); return <div className="pair-row" key={r.seed}>
      <span className="mono">Seed {r.seed}</span>
      <div className="pair-tracks">
        <div className="track"><i className="left" style={{ width: `${(f.left ?? 0) / max * 84}%` }}/><b>{fixed(f.left)}</b></div>
        <div className="track"><i className="right" style={{ width: `${(f.right ?? 0) / max * 84}%` }}/><b>{fixed(f.right)}</b></div>
      </div>
      <span className={`delta ${f.difference === null ? '' : (f.difference < 0) === lowerIsBetter ? 'positive' : f.difference === 0 ? '' : 'negative'}`}>{f.difference === null ? '—' : `${f.difference > 0 ? '+' : ''}${f.difference.toFixed(2)}`}</span>
    </div>; })}
  </div>;
}

export function Experiments({ comparison }: { comparison: Comparison | null }) {
  if (!comparison) return <div className="panel empty"><h2>No comparison report yet</h2><p>Run the headless experiment locally to populate this view.</p><code>python -m genesis.cli compare --seeds 11 42 77 --ticks 160</code></div>;
  if (!comparison.paired) return <div className="panel empty"><h2>This report predates the current protocol</h2><p>Re-run the comparison to produce a {`paired-phase-2`} report.</p><code>python -m genesis.cli compare --seeds 11 42 77 --ticks 160</code></div>;
  const p = comparison.paired;
  return <>
    <div className="comparison-summary">
      <span><strong>{comparison.completed_runs}</strong> completed worlds</span>
      <span><strong>{comparison.failed_runs}</strong> failed attempts</span>
      <span><strong>{comparison.planned_seeds.length}</strong> paired seeds</span>
      <span><strong>{comparison.planned_ticks}</strong> ticks · removal at {comparison.removal_tick}</span>
      <span><strong>$0</strong> model spending</span>
    </div>
    <div className="lower-grid">
      <section className="panel padded"><span className="eyebrow">QUESTION 1 · SHARING − RESTRICTED</span><h2>Energy spent per alloy</h2>
        <Bars rows={p.sharing_vs_restricted ?? []} metric="energy_per_alloy" leftLabel="Sharing" rightLabel="Restricted"/>
        <p className="small-text">Sharing and restricted worlds both reach 512 alloy because finite ore runs out (1,024 ore makes at most 512). Sharing changes the energy cost of that output, not its volume. Removal worlds make slightly less: retirees' ore moves to settlement storage, which no action can withdraw yet.</p>
      </section>
      <section className="panel padded"><span className="eyebrow">QUESTION 2 · CAN KNOWLEDGE OUTLIVE ITS INVENTOR?</span><h2>Energy per alloy after removal</h2>
        <h3 className="mini-heading">With sharing</h3>
        <Bars rows={p.creator_removal_vs_matched_with_sharing ?? []} metric="energy_per_alloy_after_removal" leftLabel="Creators removed" rightLabel="Matched non-creators removed"/>
        <h3 className="mini-heading">Restricted</h3>
        <Bars rows={p.creator_removal_vs_matched_restricted ?? []} metric="energy_per_alloy_after_removal" leftLabel="Creators removed" rightLabel="Matched non-creators removed"/>
        <p className="small-text">The matched control retires the same number of workers from the same settlements, and every retiree's inventory moves to settlement storage, so the comparison isolates lost knowledge from lost labour and goods.</p>
      </section>
    </div>
    <section className="panel table-panel"><div className="panel-header"><h2>Every planned attempt</h2><span className="eyebrow">ONE WORLD = ONE EXPERIMENTAL UNIT</span></div>
      <div className="table-scroll"><table><thead><tr><th>Seed</th><th>Condition</th><th>Alloy</th><th>Energy / alloy</th><th>After removal</th><th>Verified</th><th>Adoptions</th><th>Uses after creator removal</th><th>Active</th><th>Status</th></tr></thead>
        <tbody>{comparison.attempts.map((a, i) => <tr key={i}><td className="mono">{a.seed}</td><td><span className={`condition ${a.condition.startsWith('restricted') ? 'restricted' : a.condition === 'baseline' ? 'baseline' : 'sharing'}`}/>{words(a.condition)}</td><td>{a.metrics?.produced ?? '—'}</td><td>{fixed(a.metrics?.energy_per_alloy)}</td><td>{fixed(a.metrics?.energy_per_alloy_after_removal)}</td><td>{a.metrics?.verified_artifacts ?? '—'}</td><td>{a.metrics?.adoptions ?? '—'}</td><td>{a.metrics?.uses_after_creator_removal ?? '—'}</td><td>{a.metrics?.active_population ?? '—'}</td><td title={a.failure}>{a.status}</td></tr>)}</tbody></table></div>
    </section>
    <div className="lower-grid">
      <section className="panel padded"><span className="eyebrow">INTERVENTION BOUNDARY</span><h2>What actually changes?</h2><p>{comparison.intervention_boundary}</p><p>{comparison.removal_design}</p></section>
      <section className="panel padded"><span className="eyebrow">HOW TO READ THIS</span><h2>Designed, not emergent</h2><p className="small-text">{comparison.interpretation}</p><p className="small-text">Policies are deterministic, so seeds vary the terrain and the hidden phase field but not the decision rules. Three seeds are a smoke test, not a sample size. Held-out phase cases are distinct from training cases, but a researcher still receives pass/fail feedback on each candidate.</p></section>
    </div>
  </>;
}
