import type { Artifact, Session, World } from './types';

const short = (id: string) => id.slice(0, 8);
const nameOf = (w: World, id?: string | null) => id ? (w.agents[id]?.name ?? id) : '—';
const stageTone: Record<string, string> = { acquired: 'green', failed: 'red', interrupted: 'red', expired: 'muted', offered: 'gold', instruction: 'gold', practice: 'gold' };
const fmt = (v: number | null | undefined) => v === null || v === undefined ? 'unavailable' : v.toFixed(2);

export function SessionsPanel({ world: w }: { world: World }) {
  const sessions = Object.values(w.sessions ?? {}).sort((a, b) => b.offered_tick - a.offered_tick);
  if (!sessions.length) return null;
  return <section className="panel table-panel"><div className="panel-header"><div><span className="eyebrow">TEACHING SESSIONS · CONTRACT teaching-1</span><h2>Who taught whom, and what it cost</h2></div>
    <span className="small-text">{sessions.filter(s => s.stage === 'acquired').length} acquired · {sessions.filter(s => s.stage === 'failed').length} failed · {sessions.filter(s => ['interrupted', 'expired'].includes(s.stage)).length} interrupted/expired</span></div>
    <div className="table-scroll"><table><thead><tr><th>Offered</th><th>Teacher → learner</th><th>Procedure</th><th>Stage</th><th>Instruction work (T / L of {sessions[0].required_work})</th><th>Practice</th><th>Teacher cost</th><th>Learner cost</th><th>Acquired</th><th>First independent use</th><th>Reason</th></tr></thead>
      <tbody>{sessions.map(s => <tr key={s.id}><td className="mono">t{s.offered_tick}</td><td>{nameOf(w, s.teacher)} → {nameOf(w, s.learner)}</td><td className="mono">{short(s.artifact)}</td>
        <td><span className={`pill small ${stageTone[s.stage] ?? ''}`}>{s.stage}</span></td><td>{s.teacher_work} / {s.learner_work}</td>
        <td>{s.practice.map((p, i) => <span key={i} className={p.passed ? 'positive' : 'negative'}>{p.passed ? '✓' : '×'} </span>)}{s.practice.length}/{s.practice_required}</td>
        <td>{s.costs.teacher_energy} energy · {s.costs.teacher_ticks} ticks</td><td>{s.costs.learner_energy} energy · {s.costs.learner_ticks} ticks</td>
        <td>{s.acquired_tick ? `t${s.acquired_tick}` : '—'}</td>
        <td>{s.first_independent_use ? `t${s.first_independent_use.tick} (${fmt(s.first_independent_use.cost_per_alloy)} vs ${fmt(s.first_independent_use.baseline_cost_per_alloy)} baseline)` : '—'}</td>
        <td className="small-text">{s.reason ?? ''}</td></tr>)}</tbody></table></div>
    <p className="small-text padded-x">Instruction reserves both participants (only their session step, eating or abandoning is allowed). Practice runs are real executions with the learner's own ore and energy. A lesson counts as acquired only after both practice runs cost no more per alloy than the baseline under the same conditions.</p>
  </section>;
}

function step(label: string, ok: boolean | null, detail: string) {
  return { label, ok, detail };
}

export function EvidenceTrail({ world: w, onArtifact }: { world: World; onArtifact: (id: string) => void }) {
  const sessions = Object.values(w.sessions ?? {});
  const learners = [...new Set(sessions.map(s => s.learner))];
  if (!learners.length) return null;
  const inventionFrozen = w.config.invention === 'frozen';
  return <section className="panel padded retention"><span className="eyebrow">EVIDENCE TRAIL · TEACHING TO REVISION</span><h2>Ancestor → lesson → practice → acquisition → use → revision</h2>
    <p className="small-text">Each learner's latest lesson. A step counts only when its event is committed. The first missing or failed step is shown exactly.</p>
    {learners.map(learner => {
      const mine = sessions.filter(s => s.learner === learner).sort((a, b) => b.offered_tick - a.offered_tick);
      const s: Session = mine.find(x => x.stage === 'acquired') ?? mine[0];
      const art: Artifact | undefined = w.artifacts[s.artifact];
      const revisions = Object.values(w.artifacts).filter(x => x.parent === s.artifact && x.created_tick > (s.acquired_tick ?? Infinity));
      const revision = revisions.sort((a, b) => a.created_tick - b.created_tick)[0];
      const searches = w.agents[learner]?.role === 'researcher';
      const frozen = inventionFrozen || !searches;
      const naReason = inventionFrozen ? 'not applicable: invention is frozen in this scenario' : 'not applicable: this learner is a producer and does not search';
      const steps = [
        step('Ancestor created', !!art, art ? `${nameOf(w, art.creator)} created ${short(art.id)} (gen ${art.generation}${art.cohort !== undefined ? `, cohort ${art.cohort}` : ''}; ${art.status})` : 'artifact record missing'),
        step('Teaching began', s.accepted_tick !== null && s.stage !== 'expired', s.accepted_tick ? `accepted at t${s.accepted_tick}; ${nameOf(w, s.teacher)} taught ${nameOf(w, learner)}` : `offer at t${s.offered_tick} ${s.stage === 'expired' ? 'expired unaccepted' : 'not yet accepted'}`),
        step('Learner practised', s.practice.length > 0, s.practice.length ? `${s.practice.length} supervised run(s): ${s.practice.map(p => (p.passed ? 'pass' : 'fail') + `@t${p.tick}`).join(', ')}` : s.stage === 'instruction' ? `instruction ${s.teacher_work}/${s.learner_work} of ${s.required_work}` : 'no practice run committed'),
        step('Acquisition criterion', s.assessment ? s.assessment.passed : null, s.assessment ? `${s.assessment.passed ? 'passed' : 'FAILED'} at t${s.assessment.tick}: ${s.assessment.criterion}` : s.reason ? `session ${s.stage}: ${s.reason}` : 'not yet assessed'),
        step('Independent use', !!s.first_independent_use, s.first_independent_use ? `t${s.first_independent_use.tick}: ${fmt(s.first_independent_use.cost_per_alloy)} vs ${fmt(s.first_independent_use.baseline_cost_per_alloy)} baseline cost per alloy` : 'no execution outside the session yet'),
        step('Descendant revision', revision ? true : frozen ? null : false, revision ? `${nameOf(w, revision.creator)} proposed ${short(revision.id)} at t${revision.created_tick} (${revision.origin ?? 'revision'})` : frozen ? naReason : 'no revision of this procedure proposed after acquisition'),
        step('Evaluator decision', revision ? ['admitted', 'superseded'].includes(revision.status) : frozen ? null : false, revision ? `${revision.status}${revision.validation ? ` · validation ${fmt(revision.validation.score)} vs parent ${fmt(revision.validation.parent_score)}` : ''}` : frozen ? 'not applicable' : 'no decision'),
      ];
      const firstBad = steps.findIndex(x => x.ok === false);
      return <div className="retention-row" key={learner}><div className="retention-head"><b>{nameOf(w, learner)}</b>
        <span className={`pill small ${firstBad === -1 ? 'green' : 'gold'}`}>{firstBad === -1 ? 'trail complete for its scope' : `stops at: ${steps[firstBad].label}`}</span>
        {art && <button className="text-button" onClick={() => onArtifact(art.id)}>Procedure evidence ↗</button>}</div>
        <ol className="chain">{steps.map((x, i) => <li key={x.label} className={x.ok === false && i === firstBad ? 'missing' : x.ok ? 'ok' : ''}><span>{x.ok ? '✓' : x.ok === null ? '–' : '×'}</span><b>{x.label}</b><small>{x.detail}</small></li>)}</ol></div>;
    })}
  </section>;
}

export function CohortHistory({ world: w, onArtifact }: { world: World; onArtifact: (id: string) => void }) {
  const freezes = w.lifecycle?.freezes ?? [];
  const transitions = w.lifecycle?.transitions ?? [];
  if (!freezes.length && !transitions.length) return null;
  const chain = (id: string | undefined) => {
    const out: Artifact[] = [];
    for (let a = id ? w.artifacts[id] : undefined; a; a = a.parent ? w.artifacts[a.parent] : undefined) out.unshift(a);
    return out;
  };
  const last = freezes[freezes.length - 1];
  return <section className="panel padded"><span className="eyebrow">COHORTS · FREEZES SELECTED BY VALIDATION EVIDENCE</span><h2>Generation history</h2>
    <p className="small-text">{w.config.lifecycle === 'cohorts' ? `${w.config.cohort_count} cohorts of ${w.config.cohort_ticks} ticks; earlier cohorts' library ${w.config.cross_cohort_access ? 'visible (preserved)' : 'hidden (reset)'}.` : 'Single lifecycle.'} Freeze scores are validation scores, which are adaptive. Sealed final scores exist only in experiment reports for closed runs.</p>
    <div className="table-scroll"><table className="mini-table"><thead><tr><th>Tick</th><th>Cohort</th><th>Reason</th><th>Best created by cohort</th><th>Best accessible to cohort</th></tr></thead><tbody>
      {freezes.map(f => <tr key={f.tick + f.reason}><td>t{f.tick}</td><td>{f.cohort}</td><td>{f.reason}</td>
        <td>{f.cohort_best ? <button className="text-button" onClick={() => onArtifact(f.cohort_best!.artifact)}>{short(f.cohort_best.artifact)} · {fmt(f.cohort_best.selection_score)} · gen {f.cohort_best.generation}</button> : 'none admitted'}</td>
        <td>{f.accessible_best ? <button className="text-button" onClick={() => onArtifact(f.accessible_best!.artifact)}>{short(f.accessible_best.artifact)} · {fmt(f.accessible_best.selection_score)} · cohort {f.accessible_best.cohort}</button> : 'none'}</td></tr>)}
    </tbody></table></div>
    {transitions.length > 0 && <p className="small-text">Transitions: {transitions.map(t => `t${t.tick}: ${t.retired.length} retired → cohort ${t.cohort}`).join(' · ')}</p>}
    {last?.accessible_best && <><h3 className="mini-heading">Lineage of the final accessible best</h3><div className="lineage">{chain(last.accessible_best.artifact).map(a => <div key={a.id} className="lineage-node"><span className="eyebrow">GEN {a.generation} · COHORT {a.cohort ?? 0}</span><b className="mono">{short(a.id)}</b><small>{nameOf(w, a.creator)} · {a.origin ?? ''} · val {fmt(a.validation?.score)}</small></div>)}</div></>}
  </section>;
}

export function WorkshopEvidence({ artifact: a, world: w }: { artifact: Artifact; world: World }) {
  const dev = a.development, val = a.validation;
  return <>
    <div className="evidence-columns"><section><h3>Immutable program · {a.kind}</h3><pre>{JSON.stringify(a.content.program, null, 2)}</pre>
      <div className="small-text">Origin: {a.origin} · generation {a.generation} · cohort {a.cohort ?? 0}<br/>Parent: {a.parent ? short(a.parent) : 'none'}{a.sources?.length ? ` · composed from ${a.sources.map(short).join(', ')}` : ''}<br/>Creator: {nameOf(w, a.creator)} · creation event {a.creation_event}</div></section>
      <section><h3>Development role <span className="pill small">feedback to the proposer</span></h3>
        {dev ? <><div className="evidence-totals"><span><strong>{fmt(dev.score)}</strong>development score</span><span><strong>{fmt(dev.baseline_score)}</strong>baseline</span></div><p className="small-text">{dev.objective}</p></> : <p className="small-text">Not development-tested.</p>}
        <h3>Validation role <span className="pill small gold">adaptive: proposer saw admitted / not admitted</span></h3>
        {val ? <><div className="evidence-totals"><span><strong>{fmt(val.score)}</strong>validation score</span><span><strong>{fmt(val.parent_score ?? val.baseline_score)}</strong>{val.parent_score !== null ? 'parent (same cases)' : 'baseline'}</span></div>
          <p className="small-text">{val.admitted ? 'Admitted' : 'Not admitted'}: {val.criterion}. {val.feedback_policy}.</p></> : <p className="small-text">Not submitted.</p>}
        <h3>Sealed final evaluation</h3><p className="small-text">Not available inside a world. Sealed cases are scored only after a run closes, and only for artifacts named in a freeze record. See the Experiments page.</p></section></div>
    {dev && <div className="table-scroll"><table className="evidence-table"><thead><tr><th>Phase</th><th>Humidity</th><th>Ore</th><th>Energy</th><th>Feasible</th><th>Cost</th><th>Alloy</th></tr></thead>
      <tbody>{dev.cases.map((c, i) => <tr key={i}><td>{c.phase}</td><td>{c.humidity}</td><td>{c.ore}</td><td>{c.energy}</td><td className={c.feasible ? '' : 'negative'}>{c.feasible ? 'yes' : c.reason}</td><td>{c.cost}</td><td>{c.alloy}</td></tr>)}</tbody></table></div>}
  </>;
}
