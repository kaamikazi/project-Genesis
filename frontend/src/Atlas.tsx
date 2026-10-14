import { useEffect, useRef } from 'react';
import type { World } from './types';

const W = 1000, H = 580;
const terrainColors: Record<string, string> = { water: '#172f35', grass: '#466357', forest: '#365348', hill: '#69766a' };

export function Atlas({ world, selected, onSelect }: { world: World; selected: string; onSelect: (id: string) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const positions = useRef<Record<string, { x: number; y: number }>>({});
  const hitboxes = useRef<{ id: string; x: number; y: number }[]>([]);
  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const ctx = el.getContext('2d');
    if (!ctx) return;
    const scale = Math.min(38, 890 / world.config.width, 465 / world.config.height);
    const ox = (W - scale * world.config.width) / 2, oy = (H - scale * world.config.height) / 2 + 5;
    const point = (x: number, y: number) => [ox + (x + .5) * scale, oy + (y + .5) * scale];
    const agents = Object.values(world.agents);
    const target: Record<string, { x: number; y: number }> = {};
    agents.forEach(a => {
      const [x, y] = point(a.x, a.y);
      const collocated = agents.filter(b => b.x === a.x && b.y === a.y);
      const index = collocated.findIndex(b => b.id === a.id);
      const angle = index * Math.PI * 2 / collocated.length - Math.PI / 2;
      const radius = collocated.length > 1 ? scale * .37 : 0;
      target[a.id] = { x: x + Math.cos(angle) * radius, y: y + Math.sin(angle) * radius };
    });
    const from = { ...positions.current };
    const start = performance.now();
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    let frame = 0;
    const render = (now: number) => {
      const t = reduced ? 1 : Math.min(1, (now - start) / 350);
      const ease = 1 - (1 - t) ** 3;
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = '#142a2e'; ctx.fillRect(0, 0, W, H);
      // Water contour lines are visual texture only; positions and terrain come from committed state.
      ctx.strokeStyle = '#254046'; ctx.lineWidth = .6;
      for (let x = 0; x < W; x += 32) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
      for (let y = 0; y < H; y += 32) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }
      world.terrain.forEach((row, y) => row.forEach((tile, x) => {
        if (tile === 'water') return;
        const px = ox + x * scale, py = oy + y * scale;
        ctx.fillStyle = terrainColors[tile]; ctx.fillRect(px, py, scale + .3, scale + .3);
        ctx.strokeStyle = 'rgba(181,211,168,.075)'; ctx.strokeRect(px, py, scale, scale);
        if (tile === 'forest') {
          for (let i = 0; i < 3; i++) {
            const tx = px + scale * (.25 + .24 * i), ty = py + scale * (.32 + .2 * (i % 2));
            ctx.fillStyle = i === 1 ? '#203f36' : '#294a3e';
            ctx.beginPath(); ctx.moveTo(tx, ty - scale * .16); ctx.lineTo(tx + scale * .13, ty + scale * .15); ctx.lineTo(tx - scale * .13, ty + scale * .15); ctx.fill();
          }
        }
        if (tile === 'hill') {
          ctx.strokeStyle = '#a0aa89'; ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(px + scale * .15, py + scale * .7); ctx.lineTo(px + scale * .45, py + scale * .25); ctx.lineTo(px + scale * .75, py + scale * .7); ctx.stroke();
        }
        const neighbors = [[0, -1], [1, 0], [0, 1], [-1, 0]];
        neighbors.forEach(([dx, dy], i) => {
          if (world.terrain[y + dy]?.[x + dx] === 'water') {
            ctx.strokeStyle = '#9ba77d'; ctx.lineWidth = 2;
            ctx.beginPath();
            const lines = [[px, py, px + scale, py], [px + scale, py, px + scale, py + scale], [px, py + scale, px + scale, py + scale], [px, py, px, py + scale]];
            const l = lines[i]; ctx.moveTo(l[0], l[1]); ctx.lineTo(l[2], l[3]); ctx.stroke();
          }
        });
      }));
      Object.values(world.settlements).forEach(s => {
        const [x, y] = point(s.x, s.y);
        ctx.strokeStyle = '#b9c59a55'; ctx.setLineDash([4, 5]); ctx.lineWidth = 1;
        ctx.beginPath(); ctx.ellipse(x, y, scale * 2.6, scale * 2.6, 0, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle = '#d5bf89'; ctx.fillRect(x - 9, y - 8, 18, 15);
        ctx.fillStyle = '#414d3c'; ctx.beginPath(); ctx.moveTo(x - 13, y - 8); ctx.lineTo(x, y - 20); ctx.lineTo(x + 13, y - 8); ctx.fill();
        ctx.fillStyle = '#243b34'; ctx.fillRect(x - 3, y, 6, 7);
        const ly = y - scale * 3.2;
        ctx.fillStyle = '#152a27dd'; ctx.beginPath(); ctx.roundRect(x - 62, ly - 17, 124, 41, 5); ctx.fill();
        ctx.textAlign = 'center'; ctx.font = '600 13px "Segoe UI", sans-serif'; ctx.fillStyle = '#e3e8ce'; ctx.fillText(s.name.toUpperCase(), x, ly);
        ctx.font = '10px "Segoe UI", sans-serif'; ctx.fillStyle = '#a7baac';
        ctx.fillText(`${agents.filter(a => a.home === s.id && a.status === 'active').length} inhabitants · library`, x, ly + 15);
      });
      Object.values(world.sites).forEach(s => {
        const [x, y] = point(s.x, s.y);
        ctx.fillStyle = s.resource === 'food' ? '#bfd191' : '#cdb797';
        ctx.strokeStyle = '#243c30'; ctx.lineWidth = 2;
        ctx.beginPath();
        if (s.resource === 'food') { ctx.ellipse(x, y, 4, 8, .4, 0, Math.PI * 2); }
        else { ctx.moveTo(x, y-7); ctx.lineTo(x+6, y); ctx.lineTo(x, y+7); ctx.lineTo(x-6, y); ctx.closePath(); }
        ctx.fill(); ctx.stroke();
        ctx.fillStyle = '#16352a'; ctx.fillRect(x-9, y+11, 18, 3);
        ctx.fillStyle = s.resource === 'food' ? '#bfd191' : '#cdb797'; ctx.fillRect(x-9, y+11, 18*s.stock/s.capacity, 3);
      });
      hitboxes.current = [];
      agents.forEach(a => {
        const end = target[a.id], old = from[a.id] ?? end;
        const x = old.x + (end.x-old.x)*ease, y = old.y + (end.y-old.y)*ease;
        positions.current[a.id] = { x, y }; hitboxes.current.push({ id: a.id, x, y });
        if (a.id === selected) {
          ctx.strokeStyle = '#e9d6a2'; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(x, y, 11, 0, Math.PI*2); ctx.stroke();
        }
        ctx.fillStyle = a.status !== 'active' ? '#78837d' : a.home === 'hearth' ? '#efd49d' : '#98d9cf';
        ctx.strokeStyle = '#1a302a'; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI*2); ctx.fill(); ctx.stroke();
        if (a.id === selected) {
          ctx.font = '600 11px "Segoe UI", sans-serif'; ctx.textAlign = 'center';
          ctx.fillStyle = '#14231f'; ctx.beginPath(); ctx.roundRect(x-29, y+17, 58, 22, 4); ctx.fill();
          ctx.fillStyle = '#f5e4ba'; ctx.fillText(a.name, x, y+32);
        }
      });
      ctx.fillStyle = '#809c99'; ctx.font = '10px monospace'; ctx.textAlign = 'left';
      ctx.fillText('LOCAL ATLAS / ' + world.config.width + ' × ' + world.config.height, 25, H-24);
      ctx.textAlign = 'right'; ctx.fillText('1 CELL = 1 TRAVEL UNIT', W-25, H-24);
      ctx.save(); ctx.translate(W-38, 40); ctx.strokeStyle = '#afc2af'; ctx.beginPath(); ctx.moveTo(0, 12); ctx.lineTo(0, -8); ctx.moveTo(-4, -3); ctx.lineTo(0, -8); ctx.lineTo(4, -3); ctx.stroke(); ctx.font = '10px sans-serif'; ctx.textAlign = 'center'; ctx.fillText('N', 0, -16); ctx.restore();
      if (t < 1) frame = requestAnimationFrame(render);
    };
    frame = requestAnimationFrame(render);
    return () => cancelAnimationFrame(frame);
  }, [world, selected]);
  return <canvas ref={canvas} width={W} height={H} aria-label={`World map, tick ${world.tick}. Select inhabitants using the adjacent inspector or Inhabitants tab.`} role="img"
    onClick={e => { const r = e.currentTarget.getBoundingClientRect(); const x = (e.clientX-r.left)*W/r.width, y = (e.clientY-r.top)*H/r.height; const near = [...hitboxes.current].sort((a, b) => Math.hypot(a.x-x,a.y-y)-Math.hypot(b.x-x,b.y-y))[0]; if (near && Math.hypot(near.x-x,near.y-y)<22) onSelect(near.id); }} />;
}
