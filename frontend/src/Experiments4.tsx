/* Milestone 4 reports: A (teaching and acquisition) and B (cumulative invention). All values come from the reducer,
   freeze records and the post-close sealed report; unavailable ratios are labelled, never drawn as zero. */
type R = { value: number | null; numerator: number; denominator: number } | null | undefined;
type Any = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

const f2 = (v: number | null | undefined) => v === null || v === undefined ? 'unavailable' : v.toFixed(2);
const fr = (r: R) => !r ? '—' : r.value === null ? 'unavailable' : r.value.toFixed(2);
const words = (s: string) => s.replaceAll('-', ' ').replaceAll('_', ' ');

export function TeachingReport({ report }: { report: Any }) {
  const agg: Record<string, Any> = report.aggregates ?? {};
  return <>
    <div className="panel experiment-heading"><div><span className="eyebrow">EXPERIMENT A · {String(report.protocol).toUpperCase()} · {report.label}</span>
      <h2>How do fresh successors get a procedure?</h2><p>{report.design}</p>
      <p className="small-text">Checkpoint t{report.checkpoint_tick} · boundary t{report.boundary_tick} · window {report.window.ticks} ticks · ore per site {report.ore_per_site} · {report.eligibility}</p></div>
      <span className="pill gold">EXPLORATORY · OFFLINE CONTROLLERS</span></div>
    <section className="panel table-panel"><div className="panel-header"><h2>Per condition, pooled over worlds</h2><span className="eyebrow">SUCCESSORS ARE NOT INDEPENDENT SAMPLES</span></div>
      <div className="table-scroll"><table><thead><tr><th>Condition</th><th>Worlds</th><th>Acquired</th><th>Median ticks to acquisition</th><th>Used with saving</th><th>Median ticks to saving</th>
        <th>Sessions failed / interrupted</th><th>Teaching energy (teacher / learner)</th><th>Successor energy per alloy (pooled)</th><th>Settlement production energy per alloy (mean)</th><th>Settlement charged energy per alloy (mean)</th><th>Successors active at end</th></tr></thead>
        <tbody>{Object.entries(agg).map(([k, v]: [string, Any]) => <tr key={k}><td>{words(k)}</td><td>{v.worlds}</td><td>{v.acquired}/{v.successors}</td><td>{f2(v.median_ticks_to_acquisition)}</td>
          <td>{v.used_with_saving}/{v.successors}</td><td>{f2(v.median_ticks_to_use_with_saving)}</td><td>{v.sessions_failed} / {v.sessions_interrupted}</td>
          <td>{v.teaching_energy_teacher} / {v.teaching_energy_learner}</td><td>{f2(v.successor_production_energy_per_alloy?.pooled_ratio)}</td>
          <td>{f2(v.settlement_production_energy_per_alloy?.mean_of_world_ratios)}</td><td>{f2(v.settlement_charged_energy_per_alloy?.mean_of_world_ratios)}</td><td>{v.successors_active_at_end}</td></tr>)}</tbody></table></div></section>
    <section className="panel table-panel"><div className="panel-header"><h2>Every world and continuation</h2></div>
      <div className="table-scroll"><table><thead><tr><th>Seed</th><th>Status</th><th>Parity</th><th>Continuation</th><th>Successor</th><th>Acquired (path, tick)</th><th>First saving</th><th>Successor energy per alloy</th><th>Sessions (acq / fail / int)</th><th>Settlement prod. / charged energy per alloy</th><th>Ore left</th></tr></thead>
        <tbody>{report.seeds.flatMap((s: Any) => s.status !== 'completed' && !(s.continuations ?? []).length
          ? [<tr key={s.seed}><td>{s.seed}</td><td className="negative">{s.status}</td><td colSpan={9}>{s.reason ?? s.failure ?? ''}</td></tr>]
          : s.continuations.flatMap((c: Any) => c.status !== 'completed' ? [<tr key={s.seed + c.label}><td>{s.seed}</td><td>{s.status}</td><td/><td>{words(c.label)}</td><td colSpan={7} className="negative">{c.status}: {c.failure}</td></tr>]
            : c.summary.successors.map((h: Any, i: number) => <tr key={s.seed + c.label + h.successor}>
              <td>{i === 0 ? s.seed : ''}</td><td>{i === 0 ? s.status : ''}</td><td>{i === 0 ? (s.physical_parity?.identical ? '✓' : '×') : ''}</td><td>{i === 0 ? words(c.label) : ''}</td>
              <td className="mono">{h.successor} ← {h.predecessor}</td>
              <td>{h.first_acquisition_by_teaching ? `teaching, t${h.first_acquisition_by_teaching.tick}` : h.first_library_acquisition ? `library, t${h.first_library_acquisition.tick}` : h.package?.length ? 'direct package' : 'none'}</td>
              <td>{h.first_use_with_saving ? `t${h.first_use_with_saving.tick}` : 'none'}</td><td>{fr(h.production_energy_per_alloy)}</td>
              <td>{i === 0 ? `${c.summary.sessions.acquired} / ${c.summary.sessions.failed} / ${c.summary.sessions.interrupted_or_expired}` : ''}</td>
              <td>{i === 0 ? `${fr(c.summary.settlement.production_energy_per_alloy)} / ${fr(c.summary.settlement.charged_energy_per_alloy)}` : ''}</td><td>{i === 0 ? c.summary.ore_on_sites_at_end : ''}</td></tr>)))}</tbody></table></div></section>
  </>;
}

export function CumulativeReport({ report, sealed }: { report: Any; sealed: Any | null }) {
  const sealedFor = (seed: number, cond: string) => sealed?.worlds?.find((w: Any) => w.seed === seed && w.condition === cond);
  return <>
    <div className="panel experiment-heading"><div><span className="eyebrow">EXPERIMENT B · {String(report.protocol).toUpperCase()} · {report.label}</span>
      <h2>Does preserved knowledge build across cohorts?</h2><p>{report.design}</p>
      <p className="small-text">{report.cohort_count} cohorts × {report.cohort_ticks} ticks · ore per site {report.ore_per_site} · search budget {report.search_budget_per_researcher_lifetime} proposals per researcher lifetime · selection: {report.selection_rule}</p></div>
      <span className="pill gold">EXPLORATORY · SEALED SCORES COMPUTED AFTER CLOSE</span></div>
    <section className="panel table-panel"><div className="panel-header"><h2>Frozen artifacts by cohort</h2><span className="eyebrow">VALIDATION IS ADAPTIVE · SEALED IS NOT</span></div>
      <div className="table-scroll"><table><thead><tr><th>Seed</th><th>Condition</th><th>Parity at first boundary</th><th>Sealed baseline</th>
        {[0, 1, 2].map(k => <th key={k}>Cohort {k}: created best (val / sealed)</th>)}<th>Final accessible best (val / sealed)</th><th>Cross-gen revisions (admitted / attempts)</th><th>Ore left</th></tr></thead>
        <tbody>{report.worlds.map((w: Any) => { const s = sealedFor(w.seed, w.condition); const parity = report.parity?.find((p: Any) => p.seed === w.seed);
          if (w.status !== 'completed') return <tr key={w.seed + w.condition}><td>{w.seed}</td><td>{w.condition}</td><td colSpan={8} className="negative">{w.status}: {w.failure}</td></tr>;
          const rows = s?.freezes ?? [];
          const last = rows[rows.length - 1];
          return <tr key={w.seed + w.condition}><td className="mono">{w.seed}</td><td>{w.condition}</td><td>{parity?.identical_at_first_boundary ? '✓' : '×'}</td><td>{f2(s?.baseline_sealed?.score)}</td>
            {[0, 1, 2].map(k => { const fz = rows.find((x: Any) => x.cohort === k && x.reason !== 'run closed') ?? rows.find((x: Any) => x.cohort === k);
              return <td key={k}>{fz?.cohort_best ? `${f2(fz.cohort_best.selection_score)} / ${f2(fz.cohort_best.sealed?.score)}` : 'none admitted'}</td>; })}
            <td>{last?.accessible_best ? `${f2(last.accessible_best.selection_score)} / ${f2(last.accessible_best.sealed?.score)} (cohort ${last.accessible_best.cohort})` : '—'}</td>
            <td>{w.summary.cross_generation.admitted_revisions} / {w.summary.cross_generation.revision_attempts}</td><td>{w.summary.ore_on_sites_at_end}</td></tr>; })}</tbody></table></div>
      <p className="small-text padded-x">"Created best" is the lowest-validation admitted workflow created by that cohort, chosen at the cohort's freeze. A cross-generation revision is a proposal whose parent came from an earlier cohort; admitted means it beat that parent on the same validation cases. Sealed scores use 48 cases committed before any evaluation run.</p></section>
    <section className="panel table-panel"><div className="panel-header"><h2>Costs and output per cohort</h2></div>
      <div className="table-scroll"><table><thead><tr><th>Seed</th><th>Condition</th><th>Cohort</th><th>Proposals</th><th>Admitted</th><th>Search / evaluation / learning energy</th><th>Alloy</th><th>Production energy per alloy</th><th>Charged energy per alloy</th></tr></thead>
        <tbody>{report.worlds.filter((w: Any) => w.status === 'completed').flatMap((w: Any) => w.summary.per_cohort.map((c: Any) => <tr key={w.seed + w.condition + c.cohort}>
          <td>{c.cohort === 0 ? w.seed : ''}</td><td>{c.cohort === 0 ? w.condition : ''}</td><td>{c.cohort}</td><td>{c.proposals}</td><td>{c.admitted}</td>
          <td>{c.search_energy} / {c.evaluation_energy} / {c.learning_energy}</td><td>{c.produced_alloy}</td><td>{fr(c.production_energy_per_alloy)}</td><td>{fr(c.charged_energy_per_alloy)}</td></tr>))}</tbody></table></div></section>
  </>;
}
