import type { Aggregate, Comparison, Continuation, Inheritance, Ratio } from './types';

const words = (value: string) => value.replaceAll('_', ' ').replaceAll('-', ' ');
const fmt = (r: Ratio | null | undefined) => !r ? '—' : r.value === null ? 'unavailable' : r.value.toFixed(2);
const num = (v: number | null | undefined) => v === null || v === undefined ? 'unavailable' : v.toFixed(2);

function RatioBars({ rows, unit }: { rows: { label: string; ratio: Ratio | null | undefined; tone: string }[]; unit: string }) {
  const values = rows.map(r => r.ratio?.value).filter((v): v is number => v !== null && v !== undefined);
  const max = Math.max(1e-9, ...values);
  return <div className="pair-bars">{rows.map(r => <div className="pair-row" key={r.label}>
    <span className="mono">{r.label}</span>
    <div className="track">{r.ratio?.value === null || r.ratio === undefined || r.ratio === null
      ? <span className="unavailable">unavailable{r.ratio ? ` · ${r.ratio.numerator}/${r.ratio.denominator}` : ''}</span>
      : <><i className={r.tone} style={{ width: `${(r.ratio.value / max) * 84}%` }}/><b>{r.ratio.value.toFixed(2)}</b></>}</div>
    <span/>
  </div>)}<p className="small-text">{unit}. A missing value means a zero denominator; it is never drawn as zero.</p></div>;
}

function AggregateLine({ label, a }: { label: string; a?: Aggregate }) {
  if (!a) return null;
  return <tr><td>{label}</td><td>{a.worlds_with_value}/{a.worlds}</td><td>{num(a.mean_of_world_ratios)}</td><td>{num(a.pooled_ratio)}</td></tr>;
}

function InheritanceView({ report }: { report: Inheritance }) {
  const diag = (c: Continuation) => c.summary;
  return <>
    <div className="panel experiment-heading"><div><span className="eyebrow">PROTOCOL / {report.protocol.toUpperCase()}{report.population ? ` · ${report.population} AGENTS` : ''}</span>
      <h2>Controlled succession from one checkpoint</h2><p>{report.design}</p>
      <p className="small-text">Checkpoint tick {report.checkpoint_tick} · removal boundary tick {report.removal_boundary_tick} · diagnostic window: ticks {report.diagnostic_window.start_exclusive + 1}–{report.diagnostic_window.end_inclusive} ({report.diagnostic_window.ticks} ticks) · {report.eligibility}</p></div>
      <span className="pill gold">EXPLORATORY · SIMULATED SUCCESSION</span></div>
    {report.seeds.map(seed => <section className="panel table-panel" key={seed.seed}>
      <div className="panel-header"><h2>Seed {seed.seed} <span className="subtle">/ {seed.status}</span></h2>
        <span className={`pill small ${seed.physical_parity?.identical && seed.physical_parity?.same_retirees ? 'green' : 'red'}`}>
          {seed.physical_parity ? (seed.physical_parity.identical && seed.physical_parity.same_retirees ? 'physical parity verified at boundary' : 'PARITY FAILED') : 'no parity record'}</span></div>
      {seed.reason && <p className="failure-line padded-x">Ineligible: {seed.reason}</p>}
      {seed.failure && <p className="failure-line padded-x">Failed: {seed.failure}</p>}
      <div className="table-scroll"><table><thead><tr><th>Continuation</th><th>Successor</th><th>Library acquired</th><th>First use with saving</th><th>Uses (saving / total)</th><th>Successor energy / alloy</th><th>Settlement energy / alloy</th><th>All charged energy / alloy</th><th>Ore left</th></tr></thead>
        <tbody>{seed.diagnostic.flatMap(c => c.status !== 'completed' ? [<tr key={c.label}><td>{words(c.label)}</td><td colSpan={8} className="negative">{c.status}: {c.failure}</td></tr>]
          : diag(c)!.successors.map((s, i) => <tr key={c.label + s.successor}>
            <td>{i === 0 ? words(c.label) : ''}</td><td className="mono">{s.successor} ← {s.predecessor}</td>
            <td>{s.first_library_acquisition ? `tick ${s.first_library_acquisition.tick}` : s.package.length ? 'package (control)' : 'none'}</td>
            <td>{s.first_use_with_saving ? `tick ${s.first_use_with_saving.tick} (${s.first_use_with_saving.energy} vs ${s.first_use_with_saving.baseline_energy})` : 'none'}</td>
            <td>{s.uses_with_saving} / {s.use_executions}</td><td>{fmt(s.production_energy_per_alloy)}</td>
            <td>{i === 0 ? fmt(diag(c)!.settlement_production_energy_per_alloy) : ''}</td><td>{i === 0 ? fmt(diag(c)!.settlement_charged_energy_per_alloy) : ''}</td>
            <td>{i === 0 ? `${diag(c)!.ore_on_sites_at_end}${diag(c)!.depleted ? ' (depleted)' : ''}` : ''}</td></tr>))}</tbody></table></div>
    </section>)}
    <div className="lower-grid">
      <section className="panel padded"><span className="eyebrow">AGGREGATES ACROSS WORLDS</span><h2>Successor production energy per alloy</h2>
        <table className="mini-table"><thead><tr><th>Condition</th><th>Values</th><th>Mean of ratios</th><th>Pooled ratio</th></tr></thead><tbody>
          {Object.entries(report.aggregates).filter(([k]) => k.startsWith('successor')).map(([k, v]) => <AggregateLine key={k} label={words(k)} a={v.successor_production_energy_per_alloy}/>)}
        </tbody></table>
        <p className="small-text">Successors are pooled across worlds; two successors in one world are not independent samples. The mean of ratios and the pooled ratio are labelled separately and never substituted for one another.</p></section>
      <section className="panel padded"><span className="eyebrow">LIVE CONTINUATION · SEPARATE EXPERIMENT</span><h2>Successor researchers, invention open</h2>
        <table className="mini-table"><thead><tr><th>Seed</th><th>Continuation</th><th>Prod. energy / alloy</th><th>Charged energy / alloy</th><th>Successor learned</th><th>First saving</th><th>Re-derived by search</th></tr></thead><tbody>
          {report.seeds.flatMap(s => s.live.map(c => <tr key={s.seed + c.label}><td>{s.seed}</td><td>{words(c.label)}</td><td>{c.summary ? fmt(c.summary.settlement_production_energy_per_alloy) : c.status}</td>
            <td>{c.summary ? fmt(c.summary.settlement_charged_energy_per_alloy) : '—'}{c.summary?.depleted ? ' (ore depleted)' : ''}</td>
            <td>{c.summary ? c.summary.successors.map(x => x.first_library_acquisition ? `t${x.first_library_acquisition.tick}` : 'no').join(', ') : '—'}</td>
            <td>{c.summary ? c.summary.successors.map(x => x.first_use_with_saving ? `t${x.first_use_with_saving.tick}` : 'none').join(', ') : '—'}</td>
            <td>{c.summary ? (c.summary.new_verified_creators_after_boundary.join(', ') || 'no') : '—'}</td></tr>))}</tbody></table>
        <p className="small-text">Here successors may rediscover procedures by search, so relearning and inheritance are mixed; that is why the diagnostic above freezes invention. Library successors learn first and then try revisions of the inherited procedure (all rejected, because it is already optimal). Successors without the library re-derive it by search, which costs search and evaluation energy.</p></section>
    </div>
  </>;
}

function ComparisonView({ comparison }: { comparison: Comparison }) {
  const seeds = comparison.planned_seeds;
  return <>
    <div className="panel experiment-heading"><div><span className="eyebrow">PROTOCOL / {comparison.protocol.toUpperCase()} · DESCRIPTIVE</span>
      <h2>Whole-run conditions</h2><p>{comparison.intervention_boundary}</p><p className="small-text">{comparison.removal_design}</p></div>
      <span className="pill gold">EXPLORATORY · NO SIGNIFICANCE CLAIM</span></div>
    <div className="comparison-summary">
      <span><strong>{comparison.completed_runs}</strong> completed worlds</span><span><strong>{comparison.failed_runs}</strong> failed attempts</span>
      <span><strong>{seeds.length}</strong> seeds</span><span><strong>{comparison.planned_ticks}</strong> ticks · removal at {comparison.removal_tick}</span><span><strong>$0</strong> model spending</span>
    </div>
    <section className="panel padded"><span className="eyebrow">PRODUCTION EFFICIENCY · SHARING VS RESTRICTED</span><h2>Production energy per produced alloy</h2>
      <RatioBars unit="Production energy only (excludes travel, search, evaluation and learning)" rows={seeds.flatMap(seed => ['sharing', 'restricted', 'baseline'].map(c => {
        const a = comparison.attempts.find(x => x.seed === seed && x.condition === c);
        return { label: `${seed} · ${c}`, ratio: a?.reducer?.overall.production_energy_per_alloy, tone: c === 'sharing' ? 'left' : 'right' };
      }))}/></section>
    <section className="panel table-panel"><div className="panel-header"><h2>Every planned attempt (independent reducer)</h2><span className="eyebrow">ONE WORLD = ONE EXPERIMENTAL UNIT</span></div>
      <div className="table-scroll"><table><thead><tr><th>Seed</th><th>Condition</th><th>Output: alloy</th><th>Efficiency: prod. energy / alloy</th><th>Total cost: charged energy / alloy</th><th>After removal: prod. energy / alloy</th><th>Ore left (accessible / not)</th><th>Status</th></tr></thead>
        <tbody>{comparison.attempts.map((a, i) => { const r = a.reducer; const post = r?.windows?.post_removal;
          return <tr key={i}><td className="mono">{a.seed}</td><td><span className={`condition ${a.condition.startsWith('restricted') ? 'restricted' : a.condition === 'baseline' ? 'baseline' : 'sharing'}`}/>{words(a.condition)}</td>
            <td>{r ? `${r.overall.produced_alloy} / ${r.theoretical_max_alloy_from_initial_ore} max` : '—'}</td><td>{fmt(r?.overall.production_energy_per_alloy)}</td><td>{fmt(r?.overall.charged_energy_per_alloy)}</td>
            <td>{post ? fmt(post.production_energy_per_alloy) : 'no removal'}</td><td>{r ? `${r.remaining.accessible.ore ?? 0} / ${r.remaining.inaccessible.ore ?? 0}` : '—'}</td>
            <td title={a.failure}>{a.status}</td></tr>; })}</tbody></table></div>
    </section>
    <section className="panel padded"><span className="eyebrow">HOW TO READ THIS</span><h2>Designed, not emergent</h2><p className="small-text">{comparison.interpretation}</p>
      <p className="small-text">Retirement rows are descriptive: retired creators were researchers and matched retirees were producers, so their roles and labour differ. The controlled test is the inheritance diagnostic above.</p></section>
  </>;
}

export function Experiments({ comparison, inheritance, twenty }: { comparison: Comparison | null; inheritance: Inheritance | null; twenty?: Inheritance | null }) {
  if (!comparison && !inheritance) return <div className="panel empty"><h2>No experiment reports yet</h2><p>Regenerate the evidence locally.</p><code>python tools/generate_evidence.py</code></div>;
  return <>
    {inheritance ? <InheritanceView report={inheritance}/> : <div className="panel empty"><h2>No inheritance report</h2><code>python -m genesis.cli inherit</code></div>}
    {twenty && <details className="panel padded twenty"><summary><b>Twenty-agent replication</b> <span className="small-text">({twenty.population} agents, declared ore_per_site {(twenty as Inheritance & { ore_per_site?: number }).ore_per_site ?? '?'}). Scale is not richer cognition.</span></summary><InheritanceView report={twenty}/></details>}
    {comparison?.attempts?.[0]?.reducer !== undefined || comparison?.protocol === 'paired-phase-3' ? <ComparisonView comparison={comparison!}/>
      : comparison ? <div className="panel empty"><h2>The comparison report predates the current protocol</h2><code>python -m genesis.cli compare</code></div> : null}
  </>;
}
