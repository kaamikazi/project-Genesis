/* Milestone 5 views: search attempts and budgets, component dependency graph, dependency teaching across overlapping
   generations, frozen closures, and the v0.5 experiment reports. Live panels read the observer state and the recent
   decision diagnostics; reports read the generated evidence. Unavailable values are labelled, never drawn as zero. */
import type { World } from './types';

type Any = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const short = (id?: string | null) => id ? id.slice(0, 8) : '—';
const f2 = (v: number | null | undefined) => v === null || v === undefined ? 'unavailable' : v.toFixed(2);
const words = (s: string) => s.replaceAll('-', ' ').replaceAll('_', ' ');
const nameOf = (w: World, id?: string | null) => id ? (w.agents[id]?.name ?? id) : '—';

export function SearchPanel({ world: w, diagnostics }: { world: World; diagnostics: Any[] }) {
  const cfg = w.config as Any;
  const credits = cfg.budget_unit === 'credits';
  const arts = Object.values(w.artifacts) as Any[];
  const researchers = Object.values(w.agents).filter(a => a.role === 'researcher').sort((a, b) => (a.cohort ?? 0) - (b.cohort ?? 0) || a.id.localeCompare(b.id));
  const stops: Record<string, number> = {};
  for (const d of diagnostics) if (d.stop) stops[d.stop] = (stops[d.stop] ?? 0) + 1;
  const attempts = diagnostics.filter(d => d.step && d.step !== 'stop').slice(0, 14);
  return <section className="panel table-panel">
    <div className="panel-header"><div><span className="eyebrow">SEARCH · POLICY {String(cfg.search_policy ?? 'first-improvement').toUpperCase()} · BUDGET {credits ? `${cfg.search_budget} SHARED CREDITS` : `${cfg.search_budget} PROPOSALS`}</span>
      <h2>What each researcher tried, and why it stopped</h2>{cfg.validation_policy === 'cohort-panels' && <p className="small-text">Admission: cohort panel {w.lifecycle?.cohort ?? 0} active · cap {cfg.panel_queries} submissions per researcher per panel</p>}</div>
      <span className="small-text">Stops in the last 40 ticks: {Object.keys(stops).length ? Object.entries(stops).map(([k, v]) => `${words(k)} ${v}`).join(' · ') : 'none recorded'}</span></div>
    <div className="table-scroll"><table><thead><tr><th>Researcher</th><th>Cohort</th><th>Status</th><th>{credits ? 'Credits spent' : 'Proposals'}</th><th>Own attempts (proposed / dev-tested / not admitted / admitted)</th><th>Frontier (best own or held dev scores)</th></tr></thead>
      <tbody>{researchers.map(a => {
        const own = arts.filter(x => x.creator === a.id && x.task === 'workshop-1');
        const count = (s: string) => own.filter(x => x.status === s).length;
        const notes = ((a as Any).dev_notes ?? {}) as Record<string, number>;
        const frontier = Object.entries(notes).filter(([k]) => k !== 'baseline' && w.artifacts[k]).sort((x, y) => x[1] - y[1]).slice(0, 4);
        return <tr key={a.id}><td>{a.name} <span className="mono small-text">{a.id}</span></td><td>{a.cohort ?? 0}</td><td>{a.status}</td>
          <td>{credits ? `${(a as Any).search_spent ?? 0} / ${cfg.search_budget}` : `${a.search_count} / ${cfg.search_budget}`}{(a as Any).panel_queries ? ` · panel queries ${Object.entries((a as Any).panel_queries as Record<string, number>).map(([k, v]) => `p${k}:${v}`).join(' ')}` : ''}</td>
          <td>{count('proposed')} / {count('dev-tested')} / {count('not-admitted')} / {count('admitted') + count('superseded')}</td>
          <td className="mono small-text">{frontier.length ? frontier.map(([k, v]) => `${short(k)} ${v.toFixed(2)}`).join(' · ') : '—'}{notes.baseline !== undefined ? ` (baseline ${notes.baseline.toFixed(2)})` : ''}</td></tr>; })}</tbody></table></div>
    {attempts.length > 0 && <div className="table-scroll"><table><thead><tr><th>Tick</th><th>Agent</th><th>Step</th><th>Operator</th><th>Parent</th><th>Remaining</th><th>Detail</th></tr></thead>
      <tbody>{attempts.map((d, i) => <tr key={i}><td className="mono">t{d.tick}</td><td>{nameOf(w, d.agent)}</td><td>{words(String(d.step))}</td><td className="mono">{d.operator ?? '—'}</td>
        <td className="mono">{d.parent ?? d.artifact ?? '—'}</td><td>{d.budget_remaining ?? '—'}</td>
        <td className="small-text">{d.guard ? `guard: ${d.guard} · ` : ''}{d.reference_status ? `reference ${d.reference_status} · ` : ''}{d.novelty_rejected ? `novelty skipped ${d.novelty_rejected} (${d.novelty_point_evaluations} point evaluations) · ` : ''}{d.stop === 'reserve' ? `reserve: ${d.budget_remaining} credits, ${d.ticks_left} ticks left · ` : ''}{d.restart ? 'restart by recombination · ' : ''}{d.dev !== undefined ? `dev ${f2(d.dev)} vs best ${f2(d.champion_dev)}` : ''}{d.component ? `component ${d.component}` : ''}</td></tr>)}</tbody></table></div>}
    <p className="small-text padded-x">Diagnostics are written by the controller with each decision and stored in tick records, not in world state. Development scores are the agent's own permitted feedback; validation returns one admitted/not-admitted bit.</p>
  </section>;
}

export function ComponentGraph({ world: w, onArtifact }: { world: World; onArtifact: (id: string) => void }) {
  const arts = Object.values(w.artifacts) as Any[];
  const comps = arts.filter(a => a.kind === 'component').sort((a, b) => a.created_tick - b.created_tick);
  const callers = arts.filter(a => a.kind === 'workflow' && (a.closure ?? []).length).sort((a, b) => a.created_tick - b.created_tick);
  if (!comps.length) return null;
  const rowH = 30, height = Math.max(comps.length, callers.length) * rowH + 20;
  const cy = (i: number) => 20 + i * rowH;
  const tone = (s: string) => s === 'admitted' ? 'var(--green)' : s === 'superseded' ? 'var(--teal)' : s === 'not-admitted' ? 'var(--red)' : 'var(--faint)';
  return <section className="panel padded">
    <div className="panel-header"><div><span className="eyebrow">COMPONENTS · CLOSURES BY HASH</span><h2>Which workflows call which components</h2></div>
      <span className="small-text">{comps.filter(c => c.origin === 'component-extraction').length} extracted · {comps.filter(c => c.origin === 'component-revision').length} revisions · {callers.filter(c => c.validation?.admission_path === 'refactor').length} refactor admissions · {callers.filter(c => c.validation?.admitted && c.validation?.admission_path !== 'refactor').length} improvement admissions</span></div>
    <div className="table-scroll"><svg role="img" aria-label="Component dependency graph" width="100%" viewBox={`0 0 640 ${height}`} style={{ minWidth: 520 }}>
      {callers.map((wf, j) => (wf.closure as string[]).map(dep => { const i = comps.findIndex(c => c.id === dep); return i < 0 ? null :
        <line key={wf.id + dep} x1={250} y1={cy(i)} x2={390} y2={cy(j)} stroke="var(--border-strong)" strokeWidth={1.5}/>; }))}
      {comps.filter(c => c.parent).map(c => { const i = comps.findIndex(x => x.id === c.id), k = comps.findIndex(x => x.id === c.parent); return k < 0 ? null :
        <path key={'p' + c.id} d={`M 20 ${cy(k)} C 0 ${cy(k)}, 0 ${cy(i)}, 20 ${cy(i)}`} fill="none" stroke="var(--teal)" strokeDasharray="3 3"/>; })}
      {comps.map((c, i) => <g key={c.id} onClick={() => onArtifact(c.id)} style={{ cursor: 'pointer' }}><circle cx={30} cy={cy(i)} r={6} fill={tone(c.status)}/>
        <text x={42} y={cy(i) + 4} fill="var(--text)" fontSize={12}>{short(c.id)} · {c.content.program.field} · {words(c.origin ?? '')} · {c.status} · {nameOf(w, c.creator)} (c{c.cohort ?? 0})</text></g>)}
      {callers.map((wf, j) => <g key={wf.id} onClick={() => onArtifact(wf.id)} style={{ cursor: 'pointer' }}><rect x={390} y={cy(j) - 7} width={12} height={12} fill={tone(wf.status)}/>
        <text x={408} y={cy(j) + 4} fill="var(--text)" fontSize={12}>{short(wf.id)} · {wf.status}{wf.validation?.admission_path === 'refactor' ? ' (refactor)' : ''} · c{wf.cohort ?? 0}</text></g>)}
    </svg></div>
    <p className="small-text">Left: components (dashed arcs link a revision to its parent). Right: workflows whose dependency closure is non-empty. An extraction equals an existing field and is refactoring, not discovery; a revision changes behaviour and is admitted only if strictly better inside its host. A call names an immutable hash, so revising a component never changes workflows that call the old one.</p>
  </section>;
}

export function GenerationsPanel({ world: w }: { world: World }) {
  const lc = (w.lifecycle ?? {}) as Any;
  const transitions: Any[] = lc.transitions ?? [];
  const cfg = w.config as Any;
  if (cfg.lifecycle !== 'cohorts') return null;
  const sessions = Object.values(w.sessions ?? {}) as Any[];
  const cohortOf = (id: string) => w.agents[id]?.cohort ?? 0;
  const cross = sessions.filter(s => cohortOf(s.teacher) !== cohortOf(s.learner));
  const paths = (Object.values(w.artifacts) as Any[]).flatMap(a => (a.transmissions ?? []).filter((t: Any) => cohortOf(t.from) !== cohortOf(t.to))
    .map((t: Any) => ({ ...t, artifact: a.id, kind: a.kind ?? 'workflow' }))).sort((a, b) => a.tick - b.tick);
  const total = cfg.cohort_ticks * cfg.cohort_count;
  return <section className="panel padded">
    <div className="panel-header"><div><span className="eyebrow">GENERATIONS · OVERLAP {cfg.cohort_overlap ?? 0} TICKS · TEACHING POLICY {String(cfg.teaching_policy ?? 'strict-prerequisites').toUpperCase()}</span><h2>Arrivals, retirements and what crossed between generations</h2></div>
      <span className="small-text">{cross.length} cross-generation lessons · {cross.filter(s => s.stage === 'acquired').length} acquired · {cross.filter(s => s.stage === 'failed').length} failed · {cross.filter(s => ['interrupted', 'expired'].includes(s.stage)).length} interrupted/expired</span></div>
    <svg role="img" aria-label="Cohort timeline" width="100%" viewBox="0 0 600 46">
      {Array.from({ length: cfg.cohort_count }, (_, k) => { const start = Math.max(0, k * cfg.cohort_ticks - (k ? (cfg.cohort_overlap ?? 0) : 0)); const end = (k + 1) * cfg.cohort_ticks;
        return <g key={k}><rect x={start / total * 600} y={4 + (k % 2) * 18} width={(end - start) / total * 600} height={14} rx={4} fill={k % 2 ? 'var(--teal-bg)' : 'var(--gold-bg)'} stroke="var(--border-strong)"/>
          <text x={start / total * 600 + 6} y={15 + (k % 2) * 18} fontSize={10} fill="var(--text)">cohort {k}</text></g>; })}
      <line x1={w.tick / total * 600} x2={w.tick / total * 600} y1={0} y2={46} stroke="var(--red)"/>
    </svg>
    <div className="table-scroll"><table><thead><tr><th>Tick</th><th>Phase</th><th>Cohort</th><th>Arrived</th><th>Retired</th></tr></thead>
      <tbody>{transitions.map((t, i) => <tr key={i}><td className="mono">t{t.tick}</td><td>{t.phase ?? 'replacement'}</td><td>{t.cohort}</td><td>{t.successors.length}</td><td>{t.retired.length}</td></tr>)}</tbody></table></div>
    {cross.length > 0 && <div className="table-scroll"><table><thead><tr><th>Offered</th><th>Teacher (cohort) → learner (cohort)</th><th>Procedure</th><th>Closure</th><th>Taught in package / already known</th><th>Stage</th><th>Reason</th></tr></thead>
      <tbody>{cross.sort((a, b) => a.offered_tick - b.offered_tick).map(s => <tr key={s.id}><td className="mono">t{s.offered_tick}</td>
        <td>{nameOf(w, s.teacher)} ({cohortOf(s.teacher)}) → {nameOf(w, s.learner)} ({cohortOf(s.learner)})</td><td className="mono">{short(s.artifact)}</td>
        <td className="mono">{(s.closure ?? []).map(short).join(', ') || 'none'}</td><td>{(s.package ?? []).length} / {(s.already_known ?? []).length}</td>
        <td>{s.stage}</td><td className="small-text">{s.reason ?? ''}</td></tr>)}</tbody></table></div>}
    {paths.length > 0 && <><h3>Knowledge paths across cohorts</h3><ul className="small-text">{paths.slice(0, 20).map((p, i) => <li key={i}>t{p.tick}: {p.kind} <span className="mono">{short(p.artifact)}</span> {nameOf(w, p.from)} (c{cohortOf(p.from)}) → {nameOf(w, p.to)} (c{cohortOf(p.to)}) via {p.via}</li>)}</ul></>}
    <p className="small-text">The schedule is identical in every condition: successors arrive before the boundary and seniors retire at it even if a lesson is unfinished (the lesson is then interrupted). Library acquisitions are logged by inspection; only teaching paths are listed here.</p>
  </section>;
}

export function FrozenClosures({ world: w }: { world: World }) {
  const freezes = ((w.lifecycle as Any)?.freezes ?? []) as Any[];
  if (!freezes.length) return null;
  const cell = (pick: Any) => !pick ? 'none' : `${short(pick.artifact)} · val ${f2(pick.selection_score)} · dev ${f2(pick.dev_score)} · c${pick.cohort} · closure ${(pick.closure ?? []).length ? (pick.closure as string[]).map(short).join(', ') : 'none'}`;
  return <section className="panel table-panel"><div className="panel-header"><div><span className="eyebrow">FREEZES · SELECTED BY VALIDATION BEFORE ANY FINAL SCORE</span><h2>Frozen workflows and their dependency closures</h2></div></div>
    <div className="table-scroll"><table><thead><tr><th>Tick</th><th>Cohort</th><th>Reason</th><th>Created by cohort</th><th>Accessible (library view)</th><th>Held by members</th></tr></thead>
      <tbody>{freezes.map((f, i) => <tr key={i}><td className="mono">t{f.tick}</td><td>{f.cohort}</td><td>{f.reason}</td><td className="small-text">{cell(f.cohort_best)}</td><td className="small-text">{cell(f.accessible_best)}</td><td className="small-text">{cell(f.held_best)}</td></tr>)}</tbody></table></div>
    <p className="small-text padded-x">Validation scores are observer-only (agents receive one bit). Sealed-2 scores are computed after a run closes, from the frozen hash and its closure, and appear only in experiment reports.</p></section>;
}

function Comparisons({ rows }: { rows: Any[] }) {
  return <div className="table-scroll"><table><thead><tr><th>A vs B</th><th>Metric (lower is better)</th><th>A lower</th><th>B lower</th><th>Ties</th><th>Mean A</th><th>Mean B</th><th>Verdict (≥4 of 5)</th></tr></thead>
    <tbody>{rows.map((c, i) => <tr key={i}><td>{c.a} vs {c.b}</td><td>{words(c.metric)}</td><td>{c.a_lower}</td><td>{c.b_lower}</td><td>{c.ties}</td><td>{f2(c.mean_a)}</td><td>{f2(c.mean_b)}</td>
      <td className={c.verdict_under_frozen_rule === 'no consistent difference' ? '' : 'positive'}>{c.verdict_under_frozen_rule}</td></tr>)}</tbody></table></div>;
}

function Totals({ totals, keys }: { totals: Record<string, Any>; keys: string[] }) {
  return <div className="table-scroll"><table><thead><tr><th>Condition</th>{keys.map(k => <th key={k}>{words(k)}</th>)}</tr></thead>
    <tbody>{Object.entries(totals).map(([c, t]) => <tr key={c}><td>{c}</td>{keys.map(k => <td key={k}>{t[k] ?? '—'}</td>)}</tr>)}</tbody></table></div>;
}

export function Milestone5Reports({ m5 }: { m5: Any | null }) {
  if (!m5?.summary) return <div className="panel empty"><h2>v0.5.0 experiments not generated</h2><code>python tools/generate_evidence_m5.py</code></div>;
  const { P, T } = m5.summary;
  const demo = m5.demonstration;
  return <>
    {P && <section className="panel table-panel"><div className="panel-header"><div><span className="eyebrow">EXPERIMENT P · SEARCH POLICY × ACCESS · {m5.protocol?.evaluation_seeds?.length ?? '?'} NEW WORLDS · SAME CREDIT POOL</span>
      <h2>Is beam search stronger than the v0.4 reference under the same budget?</h2></div><span className="pill gold">EXPLORATORY · SEALED-2 AFTER CLOSE</span></div>
      <Comparisons rows={P.comparisons}/>
      <Totals totals={P.totals} keys={['worlds', 'proposals', 'submissions', 'improvement_admissions', 'refactor_admissions', 'component_extractions', 'component_revisions', 'calling_workflow_admissions', 'executions_with_dependencies_by_later_cohort', 'cross_generation_admitted_revisions']}/>
      <p className="small-text padded-x">Held best = the best admitted workflow held by the final cohort's members at the final freeze, selected by validation. Sealed-2: 48 cases committed before any evaluation run, disjoint from development, validation and sealed-1.</p></section>}
    {T && <section className="panel table-panel"><div className="panel-header"><div><span className="eyebrow">EXPERIMENT T · TEACHING ACROSS OVERLAPPING GENERATIONS · BEAM SEARCH</span>
      <h2>Does knowledge cross generations, and does it lead to further improvement?</h2></div><span className="pill gold">EXPLORATORY</span></div>
      <Comparisons rows={T.comparisons}/>
      <Totals totals={T.totals} keys={['worlds', 'cross_generation_sessions', 'cross_generation_acquired', 'cross_generation_failed', 'cross_generation_interrupted', 'dependencies_taught_in_package', 'dependencies_acquired', 'uses_of_earlier_cohort_artifacts', 'cross_generation_admitted_revisions']}/>
      <p className="small-text padded-x">Cohort transitions where the new cohort's own best beat the previous cohort's held best: {Object.entries(T.further_improvement_transitions ?? {}).map(([k, v]) => `${k} ${v}/10`).join(' · ')}.</p></section>}
    {m5.diagnosis && <section className="panel table-panel"><div className="panel-header"><div><span className="eyebrow">SEARCH DIAGNOSIS · ALL RESEARCHER LIFETIMES · FROM STORED EXPORTS</span>
      <h2>Where the credits went, and how scores moved from development to sealed</h2></div></div>
      <div className="table-scroll"><table><thead><tr><th>Experiment / condition</th><th>Credits spent / available</th><th>Proposals · own tests · re-tests · component tests · submissions</th>
        <th>Novel evaluations</th><th>Repeated results (different program, same decisions)</th><th>Novel per 100 credits</th><th>Energy pauses (temporary / sustained ticks)</th><th>Unspent credits</th>
        <th>Final held best: dev / validation / sealed (means)</th><th>Inherited-reference admissions (better / not better on sealed)</th></tr></thead>
        <tbody>{(['policy', 'teaching'] as const).flatMap(exp => Object.entries((m5.diagnosis[exp] ?? {}) as Record<string, Any>).map(([c, d]) => { const inh = m5.inherited?.experiments?.[exp]?.by_condition?.[c];
          return <tr key={exp + c}><td>{exp === 'policy' ? 'P' : 'T'} · {c}</td><td>{d.credits_spent} / {d.credits_available}</td>
          <td>{d.allocation.propose} · {d.allocation['own-candidate test']} · {d.allocation['re-test of held']} · {d.allocation['component test']} · {d.allocation.submit}</td>
          <td>{d.novel_evaluations}</td><td>{d.repeated_evaluation_results}</td><td>{d.novel_per_100_credits}</td>
          <td>{d.energy_pauses.temporary_ticks} / {d.energy_pauses.sustained_ticks}</td><td>{d.unspent_credits.total}</td>
          <td>{f2(d.scores.mean_dev)} / {f2(d.scores.mean_validation)} / {f2(d.scores.mean_sealed)}</td>
          <td>{inh ? `${inh.admitted_improvements} (${inh.admitted_and_better_on_sealed} / ${inh.admitted_but_worse_or_equal_on_sealed})` : '—'}</td></tr>; }))}</tbody></table></div>
      <p className="small-text padded-x">Novel = an own-candidate development test whose decisions on the 24 development cases the agent had not seen before. Sealed scores of non-frozen inherited revisions are a post-hoc diagnostic computed after every run closed. {m5.patch_audit ? `Generation-patch audit: ${m5.patch_audit.worlds_compared} worlds re-run from the clean commit, ${m5.patch_audit.all_identical ? 'all identical' : 'DIFFERENCES FOUND'}.` : ''}</p></section>}
    {demo && <section className="panel table-panel"><div className="panel-header"><div><span className="eyebrow">{String(demo.label).toUpperCase()}</span><h2>One component across a generational handoff (seed {demo.seed})</h2></div></div>
      <div className="table-scroll"><table><thead><tr><th>Tick</th><th>Agent</th><th>Action</th><th>Note</th><th>Outcome</th></tr></thead>
        <tbody>{(demo.steps as Any[]).filter(s => !['walk', 'gather food', 'gather ore', 'eat'].includes(s.note)).map((s, i) => <tr key={i}><td className="mono">t{s.tick}</td><td className="mono">{s.agent}</td><td>{words(s.action)}</td><td>{s.note}</td>
          <td className="small-text">{[s.origin, s.admitted !== undefined ? (s.admitted ? 'admitted' : 'not admitted') : null, s.admission_path, s.stage, s.dev_score !== undefined ? `dev ${f2(s.dev_score)}` : null,
            s.host_dev_score !== undefined ? `host ${f2(s.host_dev_score)}` : null, s.package?.length ? `package ${s.package.length}` : null, s.dependencies_acquired?.length ? `deps acquired ${s.dependencies_acquired.length}` : null].filter(Boolean).join(' · ')}</td></tr>)}</tbody></table></div>
      <p className="small-text padded-x">Scripted actions are submitted overrides validated by the ordinary rules; every other agent runs the offline controller. This shows the mechanism works end to end; it is not evidence that it arises unprompted.</p></section>}
    {(m5.search_cpu || m5.restart) && <section className="panel padded"><span className="eyebrow">COSTS AND DURABILITY</span>
      {m5.search_cpu && <div className="table-scroll"><table><thead><tr><th>Policy</th><th>Mean ms per decision</th><th>Mean ms per proposal decision</th><th>p95 ms per proposal decision</th><th>Seconds per 180-tick run</th></tr></thead>
        <tbody>{Object.entries(m5.search_cpu.policies as Record<string, Any>).map(([k, v]) => <tr key={k}><td>{k}</td><td>{v.mean_ms_per_decision}</td><td>{v.mean_ms_per_proposal_decision ?? '—'}</td><td>{v.p95_ms_per_proposal_decision ?? '—'}</td><td>{v.mean_run_seconds_180_ticks}</td></tr>)}</tbody></table></div>}
      {m5.restart && <ul className="small-text">{(m5.restart.checks as Any[]).map((c, i) => <li key={i} className={c.passed ? 'positive' : 'negative'}>{c.passed ? '✓' : '×'} {c.check}</li>)}</ul>}</section>}
  </>;
}

function PairTable({ rows }: { rows: Any[] }) {
  return <div className="table-scroll"><table><thead><tr><th>A vs B</th><th>Metric (lower is better)</th><th>Expected</th><th>Eligible</th><th>A lower</th><th>B lower</th><th>Ties</th><th>Mean A / B (eligible)</th><th>Missing</th><th>Verdict</th></tr></thead>
    <tbody>{rows.map((c, i) => <tr key={i}><td>{c.a} vs {c.b}</td><td>{words(c.metric)}</td><td>{c.expected_worlds}</td><td>{c.eligible_pairs}</td><td>{c.a_lower}</td><td>{c.b_lower}</td><td>{c.ties}</td>
      <td>{f2(c.mean_a_over_eligible)} / {f2(c.mean_b_over_eligible)}</td><td className="small-text">{(c.missing as Any[]).map(m => `${m.seed}: ${m.reason}`).join('; ') || '—'}</td>
      <td className={c.verdict.startsWith('no ') || c.verdict.startsWith('insufficient') ? '' : 'positive'}>{c.verdict}</td></tr>)}</tbody></table></div>;
}

export function Milestone5bReports({ m5b }: { m5b: Any | null }) {
  if (!m5b?.summary && !m5b?.bugfix) return <div className="panel empty"><h2>v0.5.1 (M5b) evidence not generated</h2><code>python tools/generate_evidence_m5b.py</code></div>;
  const s = m5b.summary ?? {};
  const totals = (name: string, keys: string[]) => s[name] && <div className="table-scroll"><table><thead><tr><th>Condition</th>{keys.map(k => <th key={k}>{words(k)}</th>)}</tr></thead>
    <tbody>{Object.entries(s[name].totals as Record<string, Any>).map(([c, t]) => <tr key={c}><td>{c}</td>{keys.map(k => <td key={k}>{t[k] ?? '—'}</td>)}</tr>)}</tbody></table></div>;
  return <>
    {m5b.bugfix && <section className="panel table-panel"><div className="panel-header"><div><span className="eyebrow">DEFECT REPAIRS · MINIMAL REPRODUCTIONS · v0.5.0 vs v0.5.1</span><h2>What the repairs change</h2></div></div>
      <div className="table-scroll"><table><thead><tr><th>Scenario</th><th>Rejected actions in 10 ticks, v0.5.0</th><th>After repair</th></tr></thead>
        <tbody>{Object.entries(m5b.bugfix.summary as Record<string, Any>).map(([k, v]) => <tr key={k}><td>{words(k)}</td><td>{v.rejected_before}</td><td>{v.rejected_after}</td></tr>)}</tbody></table></div>
      <p className="small-text padded-x">The original v0.5.0 results stay as published, run with these defects. Repaired reruns are labelled separately and are retrospective.</p></section>}
    {s.allocation && <section className="panel table-panel"><div className="panel-header"><div><span className="eyebrow">ALLOCATION EXPERIMENT · PROSPECTIVE · SEALED-3 AFTER CLOSE</span>
      <h2>Does the allocation bundle help the repaired beam under the same budget?</h2></div><span className="pill gold">BUNDLE EFFECT, NOT PER-GUARD</span></div>
      <PairTable rows={s.allocation.comparisons}/>
      {totals('allocation', ['worlds_completed', 'search.credit_actions', 'search.repeated_decisions_own', 'search.novelty_rejected_candidates', 'search.untested_proposals', 'search.reserve_stops', 'admission.improvement_admissions', 'further_improved_validation', 'further_improved_sealed', 'further_compared', 'production.alloy'])}</section>}
    {s.mentorship && <section className="panel table-panel"><div className="panel-header"><div><span className="eyebrow">MENTORSHIP EXPERIMENT · PROSPECTIVE · SAME SCHEDULE IN EVERY CONDITION</span>
      <h2>Did dependency lessons get a fair chance to finish?</h2></div></div>
      <PairTable rows={s.mentorship.comparisons}/>
      {totals('mentorship', ['worlds_completed', 'eligible_transitions', 'cross_generation_lessons', 'cross_generation_acquired', 'cross_generation_failed', 'cross_generation_interrupted', 'dependency_lessons', 'dependency_lessons_acquired', 'dependencies_acquired', 'independent_post_retirement_executions_of_taught_dependency_workflows', 'further_improved_sealed'])}
      <p className="small-text padded-x">Eligible transition: a senior cohort created an admitted component-calling workflow before its boundary. Zero eligible transitions is not a teaching failure.</p></section>}
    {m5b.speed && <section className="panel table-panel"><div className="panel-header"><div><span className="eyebrow">SERVER CLOCK · TARGET 10 TICKS/S · DURABILITY UNCHANGED</span><h2>Achieved speed at base and peak population</h2></div></div>
      <div className="table-scroll"><table><thead><tr><th>Base population</th><th>Overlap</th><th>Active agents</th><th>Achieved ticks/s</th><th>Step ms</th><th>Max lag s</th></tr></thead>
        <tbody>{(m5b.speed.cases as Any[]).map((c, i) => <tr key={i}><td>{c.base_population}</td><td>{c.overlap}</td><td>{(c.active_agents_seen as number[]).join(', ')}</td><td>{c.achieved_ticks_per_second_median ?? '—'}</td><td>{c.last_step_ms_median ?? '—'}</td><td>{c.max_lag_seconds ?? '—'}</td></tr>)}</tbody></table></div></section>}
  </>;
}

function CountsTable({ counts }: { counts: Record<string, Any> }) {
  return <div className="table-scroll"><table><thead><tr><th>Condition</th><th>Expected</th><th>Completed</th><th>Failed</th><th>Shared from primary</th><th>Distinct combinations</th></tr></thead>
    <tbody>{Object.entries(counts).map(([c, v]) => <tr key={c}><td>{c}</td><td>{v.expected}</td><td>{v.completed}</td><td>{v.failed}</td><td>{v.shared_from_primary}</td><td>{v.distinct_combinations}</td></tr>)}</tbody></table></div>;
}

function PairTableC({ rows }: { rows: Any[] }) {
  return <div className="table-scroll"><table><thead><tr><th>A vs B</th><th>Metric (lower is better)</th><th>Expected (distinct)</th><th>Eligible (distinct)</th><th>A lower</th><th>B lower</th><th>Ties</th><th>Median A−B</th><th>Missing</th><th>Verdict</th></tr></thead>
    <tbody>{rows.map((c, i) => <tr key={i}><td>{c.a} vs {c.b}</td><td>{words(c.metric)}</td><td>{c.expected_worlds} ({c.distinct_parameter_combinations_expected})</td><td>{c.eligible_pairs} ({c.distinct_parameter_combinations_eligible})</td>
      <td>{c.a_lower}</td><td>{c.b_lower}</td><td>{c.ties}</td><td>{f2(c.median_difference)}</td><td className="small-text">{(c.missing as Any[]).map(m => `${m.seed}: ${m.reason}`).join('; ') || '—'}</td>
      <td className={String(c.verdict).startsWith('no ') || String(c.verdict).startsWith('insufficient') ? '' : 'positive'}>{c.verdict}</td></tr>)}</tbody></table></div>;
}

export function Milestone5cReports({ m5c }: { m5c: Any | null }) {
  if (!m5c?.manifest) return <div className="panel empty"><h2>v0.5.2 (M5c) evidence not generated</h2><code>python tools/generate_evidence_m5c.py</code></div>;
  const s = m5c.summary ?? {};
  const ev = (m5c.manifest.blocks as Any[]).filter(b => b.role === 'evaluation');
  return <>
    <section className="panel table-panel"><div className="panel-header"><div><span className="eyebrow">WORLD MANIFEST · {m5c.manifest.version} · PREFLIGHT {m5c.preflight?.passed ? 'PASSED' : 'NOT PASSED'}</span>
      <h2>{ev.length} paired evaluation worlds, {new Set(ev.map(b => b.hidden_combo.join(','))).size} distinct hidden combinations of {m5c.manifest.family.size}</h2></div></div>
      <div className="table-scroll"><table><thead><tr><th>Block</th><th>Role</th><th>Hidden combination (split, offset, flux)</th></tr></thead>
        <tbody>{(m5c.manifest.blocks as Any[]).map(b => <tr key={b.block}><td className="mono">{b.block}</td><td>{b.role}</td><td className="mono">{b.hidden_combo.join(', ')}</td></tr>)}</tbody></table></div>
      <p className="small-text padded-x">Every condition in a block starts from the same physical world and hidden parameters, with the same controller stream; streams differ across blocks. Seeds are kept in the manifest for researchers and are never shown to agents. One controller realisation per combination: controller and environment variation are partly confounded.</p></section>
    {s.primary?.comparisons && <section className="panel table-panel"><div className="panel-header"><div><span className="eyebrow">PRIMARY · ADMISSION POLICY UNDER PRESERVED KNOWLEDGE · SEALED-4 AFTER CLOSE</span>
      <h2>Do cohort-specific admission panels change what gets frozen?</h2></div></div>
      <CountsTable counts={s.primary.counts}/><PairTableC rows={s.primary.comparisons}/>
      <p className="small-text padded-x">Final picks are chosen on one shared selection panel in every condition (observer-side), so champions are comparable across admission policies. Admission scores from different panels are never compared.</p></section>}
    {s.ablation?.comparisons ? <section className="panel table-panel"><div className="panel-header"><div><span className="eyebrow">SECONDARY · ALLOCATION LEAVE-ONE-OUT · FIXED ADMISSION · beam/fixed SHARED WITH PRIMARY</span>
      <h2>Which guard of the allocation bundle matters, given the others?</h2></div></div>
      <CountsTable counts={s.ablation.counts}/><PairTableC rows={s.ablation.comparisons}/>
      <p className="small-text padded-x">Each leave-one-out contrast estimates the removed guard's effect conditional on the other guards; interactions remain possible.</p></section>
      : m5c.deferred && <div className="panel empty"><h2>Allocation ablations: planned, not executed</h2><p>{m5c.deferred.reason}</p></div>}
    {m5c.sizes && <p className="small-text">Evidence size (excluding databases): {(m5c.sizes.total_bytes_committed_estimate / 1e6).toFixed(1)} MB.</p>}
  </>;
}
