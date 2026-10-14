import type { Agent, Artifact, Use, World } from './types';

const short = (id: string) => id.slice(0, 8);
const nameOf = (w: World, id?: string | null) => id ? (w.agents[id]?.name ?? id) : '—';
const policyLabel: Record<string, string> = { library: 'settlement library access', none: 'no library access', direct: 'direct transfer (debug control)' };

export function SettlementStores({ world }: { world: World }) {
  return <section className="panel padded"><span className="eyebrow">SETTLEMENT STORAGE</span><h2>Communal stores</h2>
    <p className="small-text">Unlimited capacity. Members, meaning agents whose home it is, may deposit and withdraw within 2 tiles, whether or not the world shares knowledge. Each withdrawal is checked against stock at the moment it resolves.</p>
    <div className="stores">{Object.values(world.settlements).map(s => {
      const members = Object.values(world.agents).filter(a => a.home === s.id && a.status === 'active').length;
      return <div className="store" key={s.id}><div className="store-head"><b>{s.name}</b><small>{members} active members · {s.access ?? 'members'}</small></div>
        <table className="mini-table"><thead><tr><th/><th>Food</th><th>Ore</th><th>Alloy</th></tr></thead><tbody>
          <tr><td>In store</td>{(['food', 'ore', 'alloy'] as const).map(r => <td key={r}><b>{s.inventory[r]}</b></td>)}</tr>
          {s.flows && (['retirement', 'deposit', 'withdraw'] as const).map(k => <tr key={k}><td>{k === 'retirement' ? 'From retirees' : k === 'deposit' ? 'Deposited' : 'Withdrawn'}</td>{(['food', 'ore', 'alloy'] as const).map(r => <td key={r}>{s.flows![k][r]}</td>)}</tr>)}
        </tbody></table>
        {members === 0 && <p className="failure-line">No active members, so these goods are currently inaccessible.</p>}
      </div>;
    })}</div>
  </section>;
}

export function LineageLinks({ agent: a, world: w, select }: { agent: Agent; world: World; select: (id: string) => void }) {
  if (!a.predecessor && !a.successor && a.status !== 'retired') return null;
  return <div className="lineage-links">
    {a.predecessor && <button onClick={() => select(a.predecessor!)}>↰ Successor of <b>{nameOf(w, a.predecessor)}</b></button>}
    {a.successor && <button onClick={() => select(a.successor!)}>↳ Succeeded by <b>{nameOf(w, a.successor)}</b></button>}
    {a.status === 'retired' && <span className="small-text">Retired at tick {a.retired_tick ?? '?'} · history archived, not inherited</span>}
    {a.inheritance && <span className="small-text">Inheritance: {policyLabel[a.inheritance.policy]} · {a.inheritance.memories_inherited} memories, {a.inheritance.skills_inherited} skills handed over</span>}
  </div>;
}

function firstSaving(artifact: Artifact, agent: string): Use | undefined {
  const first = artifact.first_uses?.[agent];
  if (first && first.energy < first.baseline_energy) return first;
  return artifact.uses.find(u => u.agent === agent && u.energy < u.baseline_energy);
}

export function RetentionPanel({ world: w, onArtifact }: { world: World; onArtifact: (id: string) => void }) {
  const successions = w.lifecycle?.successions ?? [];
  const removal = w.lifecycle?.removal;
  if (!removal || !successions.length) return null;
  return <section className="panel padded retention"><span className="eyebrow">WHY THIS COUNTS AS RETENTION</span>
    <h2>From creator to successor, step by step</h2>
    <p className="small-text">Inheritance counts only when every link below is present in committed events: who created the procedure, who retired, how the successor got access, when they learned it, their own execution, and its measured result against the fixed-mode baseline. A name appearing in memory is not enough.</p>
    {successions.map(s => {
      const heir = w.agents[s.successor];
      const learned = Object.values(w.artifacts).flatMap(art => art.transmissions.filter(t => t.to === s.successor).map(t => ({ art, t })));
      const first = learned[0];
      const use = first ? firstSaving(first.art, s.successor) : undefined;
      const anyUse = first ? first.art.first_uses?.[s.successor] : undefined;
      const steps: { label: string; ok: boolean; detail: string }[] = [
        { label: 'Creator', ok: !!first, detail: first ? `${nameOf(w, first.art.creator)} created ${short(first.art.id)} (gen ${first.art.generation}, ${first.art.evaluation?.energy ?? '?'} evaluation energy)` : 'No procedure reached this successor' },
        { label: 'Retirement', ok: removal.removed.includes(s.predecessor), detail: `${nameOf(w, s.predecessor)} retired at tick ${removal.tick} (${removal.policy === 'creators' ? 'procedure creator' : 'matched non-creator'})` },
        { label: 'Access policy', ok: s.policy !== 'none', detail: `${heir?.name ?? s.successor}: ${policyLabel[s.policy]}` },
        { label: 'Learning event', ok: !!first, detail: first ? `Tick ${first.t.tick} via ${first.t.via} (event ${first.t.event})` : 'Missing: no logged transmission to this successor' },
        { label: 'Own execution', ok: !!anyUse, detail: anyUse ? `First executed at tick ${anyUse.tick} (event ${anyUse.event})` : 'Missing: the successor has not executed it' },
        { label: 'Measured outcome', ok: !!use, detail: use ? `${use.energy} energy vs ${use.baseline_energy} for the fixed-mode baseline at phase ${use.phase} (tick ${use.tick}${use === anyUse ? ', its first execution' : '; earliest saving among the 64 most recent uses kept on the record, so the exact first saving tick comes from the reducer'})` : 'Missing: no execution with a measured saving among the recorded uses' },
      ];
      const complete = steps.every(x => x.ok);
      return <div className="retention-row" key={s.successor}>
        <div className="retention-head"><b>{heir?.name ?? s.successor}</b><span className={`pill small ${complete ? 'green' : 'gold'}`}>{complete ? 'retention demonstrated' : 'chain incomplete'}</span>
          {first && <button className="text-button" onClick={() => onArtifact(first.art.id)}>Procedure evidence ↗</button>}</div>
        <ol className="chain">{steps.map(x => <li key={x.label} className={x.ok ? 'ok' : 'missing'}><span>{x.ok ? '✓' : '·'}</span><b>{x.label}</b><small>{x.detail}</small></li>)}</ol>
      </div>;
    })}
  </section>;
}
