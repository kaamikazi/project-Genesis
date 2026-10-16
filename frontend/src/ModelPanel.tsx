/* v0.6 observer view of model-backed inhabitants. Reads /api/runs/{id}/model (sanitized). Shows the true source of every
   decision (model proposal, standing-intent execution, offline policy, explicit fallback), the fixture/recorded/live
   indicator, budgets with reservations and uncertain usage, request states, and safe transcript inspection. */
import { useEffect, useState } from 'react';

type Any = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const short = (id?: string | null) => id ? id.slice(0, 10) : '—';
const words = (s: string) => s.replaceAll('-', ' ').replaceAll('_', ' ');

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`/api${path}`);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? r.statusText);
  return r.json() as Promise<T>;
}

export function ModelPanel({ runId, tick }: { runId: string; tick: number }) {
  const [m, setM] = useState<Any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<Any | null>(null);
  useEffect(() => { get<Any>(`/runs/${runId}/model`).then(x => { setM(x); setError(null); }).catch(e => setError(e.message)); }, [runId, tick]);
  if (error) return <section className="panel padded"><span className="eyebrow">MODEL-BACKED INHABITANTS</span><p className="negative">{error}</p></section>;
  if (!m) return null;
  const p = m.profile;
  const togglePause = async () => {
    await fetch(`/api/runs/${runId}/model/pause`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ paused: !m.paused }) });
    setM(await get<Any>(`/runs/${runId}/model`));
  };
  const inspect = async (id: string) => setDetail(await get<Any>(`/runs/${runId}/model/calls/${id}`));
  const dims = ['requests', 'input_tokens', 'output_tokens', 'controller_time_ms', 'cost_micros'];
  return <section className="panel table-panel">
    <div className="panel-header"><div><span className="eyebrow">MODEL-BACKED INHABITANTS · {m.source_indicator} · {m.provider} · {p.adapter.model} · {p.endpoint_label}</span>
      <h2>Who decided, from what, at what cost</h2></div>
      <button className="button" onClick={() => void togglePause()}>{m.paused ? 'Resume model scheduling' : 'Pause model scheduling'}</button></div>
    {m.halt && <p className="negative padded-x">Halted: {m.halt}. Later decisions are labelled fallbacks.</p>}
    <p className="small-text padded-x">The engine stays authoritative: a model only proposes one action, which is parsed, schema-checked and then accepted or rejected by the ordinary rules. Fixture and mock responses are scripted; they are not evidence of model competence. Pausing stops new scheduling; it does not cancel anything at a provider.</p>
    <div className="table-scroll"><table><thead><tr><th>Agent</th><th>Latest mode</th><th>Scheduler reason</th><th>Action (outcome)</th><th>Receipt</th><th>Requests left</th><th>Tokens left (in / out)</th></tr></thead>
      <tbody>{p.agents.map((a: string) => { const ag = m.agents[a]; const l = ag.latest; return <tr key={a}><td className="mono">{a}</td>
        <td>{l ? <span className={`pill small ${l.mode === 'fallback' ? 'red' : l.mode.startsWith('model') ? 'gold' : ''}`}>{words(l.mode)}</span> : '—'}</td>
        <td className="small-text">{l?.reason ?? '—'}</td><td>{l ? `${words(l.action)} (${l.accepted ? 'accepted' : 'rejected'})` : '—'}</td>
        <td className="mono">{short(l?.receipt)}</td><td>{ag.remaining.requests}</td><td>{ag.remaining.input_tokens} / {ag.remaining.output_tokens}</td></tr>; })}</tbody></table></div>
    <div className="table-scroll"><table><thead><tr><th>Run budget</th>{dims.map(d => <th key={d}>{words(d)}</th>)}</tr></thead>
      <tbody>{['committed', 'pending', 'uncertain', 'historical'].map(k => <tr key={k}><td>{k}</td>{dims.map(d => <td key={d}>{m.run.totals[k][d]}</td>)}</tr>)}
        <tr><td><b>remaining</b></td>{dims.map(d => <td key={d}><b>{m.run.remaining[d] ?? 'not limited'}</b></td>)}</tr></tbody></table></div>
    <p className="small-text padded-x">Requests: {Object.entries(m.status_counts as Record<string, number>).map(([k, v]) => `${words(k)} ${v}`).join(' · ') || 'none yet'} · parse failures {m.parse_failures} · repairs {m.repairs} · recent fallbacks {m.fallback_decisions_recent} · recent rejected model actions {m.rejected_model_actions_recent}. Cost: {p.pricing ? `${p.pricing.currency} micro-units, pricing ${p.pricing.version}` : 'unpriced (fixture/local): no monetary claim'}. Provider latency (wall clock, separate from simulation speed): median {m.provider_latency_ms.median ?? '—'} ms over {m.provider_latency_ms.count} requests. Thinking tokens (counted inside output tokens) {m.usage_totals?.thinking_tokens ?? 0} · cached input (inside input) {m.usage_totals?.cached_input_tokens ?? 0} · rows charged at the reservation {m.usage_totals?.estimated_rows ?? 0}.</p>
    <div className="table-scroll"><table><thead><tr><th>Tick</th><th>Agent</th><th>Role</th><th>Status</th><th>Usage</th><th>Parse / fallback / done</th><th>Receipt</th><th></th></tr></thead>
      <tbody>{(m.calls as Any[]).map(c => <tr key={c.decision_id}><td className="mono">t{c.tick}</td><td className="mono">{c.agent}</td><td>{c.role}{c.attempt ? ` #${c.attempt}` : ''}</td>
        <td><span className={`pill small ${c.status === 'consumed' ? 'green' : c.status === 'outcome-unknown' || c.status.startsWith('failed') ? 'red' : ''}`}>{words(c.status)}</span></td>
        <td className="small-text">{c.usage ? `${c.usage.input_tokens ?? '—'} in / ${c.usage.output_tokens ?? '—'} out${c.usage.thinking_tokens != null ? ` (${c.usage.thinking_tokens} thinking)` : ''} · ${String(c.usage.basis).split(' ')[0]}` : c.status === 'blocked' || c.status === 'cancelled-before-dispatch' ? 'not sent (no usage)' : 'reservation held'}</td>
        <td className="small-text">{c.parse_error ?? c.fallback ?? (c.finish_reason ? `finish: ${c.finish_reason}` : c.termination ? `done: ${c.termination}` : '—')}</td><td className="mono">{short(c.receipt)}</td>
        <td><button className="text-button" onClick={() => void inspect(c.decision_id)}>inspect</button></td></tr>)}</tbody></table></div>
    {detail && <div className="padded-x"><h3>Sanitized transcript · {short(detail.decision_id)} · {words(detail.status)}</h3>
      <p className="small-text">Prompt version {detail.identity?.prompt_version} · schema {detail.identity?.schema_version} · prompt bytes {detail.input_bytes} · truncations {JSON.stringify(detail.truncations)} · returned model {detail.returned_model ?? '—'}</p>
      <pre className="transcript">{(detail.prompt ?? '').slice(0, 4000)}{(detail.prompt ?? '').length > 4000 ? '\n… (truncated for display)' : ''}</pre>
      <h3>Response used</h3><pre className="transcript">{detail.response ?? '(no response)'}</pre>
      <p className="small-text">Parsed: {detail.parsed ? JSON.stringify(detail.parsed) : `— (${detail.parse_error ?? 'none'})`}. Provider reasoning fields are never stored.</p>
      <button className="text-button" onClick={() => setDetail(null)}>close</button></div>}
  </section>;
}
