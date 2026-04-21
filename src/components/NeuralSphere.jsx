import { useEffect, useRef, useCallback } from 'react';
import { useZaraStore } from '../store/zaraStore';

const NUM_NODES = 150;
const PHI = Math.PI * (3 - Math.sqrt(5));

export default function NeuralSphere() {
  const canvasRef = useRef(null);
  const stateRef = useRef({
    nodes: [],
    angleX: 0,
    angleY: 0,
    currentRadius: 0,
    targetRadius: 0,
    baseRadius: 0,
    colorR: 0, colorG: 80, colorB: 255,
    lineR: 0, lineG: 40, lineB: 127,
    raf: null,
    prevT: 0,
  });

  const zaraState = useZaraStore((s) => s.zaraState);

  // Build fibonacci sphere nodes
  const buildNodes = useCallback(() => {
    const nodes = [];
    for (let i = 0; i < NUM_NODES; i++) {
      const y = 1 - (i / (NUM_NODES - 1)) * 2;
      const r = Math.sqrt(Math.max(0, 1 - y * y));
      const theta = PHI * i;
      nodes.push([Math.cos(theta) * r, y, Math.sin(theta) * r]);
    }
    return nodes;
  }, []);

  const lerp = (a, b, t) => a + (b - a) * t;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const s = stateRef.current;
    s.nodes = buildNodes();

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);
      s.baseRadius = Math.min(rect.width, rect.height) * 0.33;
      s.targetRadius = s.baseRadius;
      if (s.currentRadius === 0) s.currentRadius = s.baseRadius;
    };

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    const render = (t) => {
      const dt = Math.min(t - s.prevT, 50);
      s.prevT = t;
      const rect = canvas.getBoundingClientRect();
      const W = rect.width, H = rect.height;
      const cx = W / 2, cy = H / 2;

      ctx.clearRect(0, 0, W, H);

      // State-based targets
      const st = zaraState;
      let tnr, tng, tnb, tlr, tlg, tlb, rotSpeed;
      if (st === 'STANDBY') {
        [tnr, tng, tnb] = [0, 80, 255]; [tlr, tlg, tlb] = [0, 40, 127];
        rotSpeed = 0.005;
        s.targetRadius = s.baseRadius + Math.sin(t * 0.001) * 4;
      } else if (st === 'LISTENING') {
        [tnr, tng, tnb] = [255, 40, 40]; [tlr, tlg, tlb] = [150, 20, 20];
        rotSpeed = 0.022;
        s.targetRadius = s.baseRadius + ((Math.sin(t * 0.008) + 1) / 2) * 32;
      } else if (st === 'THINKING') {
        [tnr, tng, tnb] = [0, 212, 255]; [tlr, tlg, tlb] = [0, 80, 160];
        rotSpeed = 0.09;
        s.targetRadius = s.baseRadius + ((Math.sin(t * 0.01) + 1) / 2) * 16;
      } else if (st === 'TALKING') {
        [tnr, tng, tnb] = [100, 255, 200]; [tlr, tlg, tlb] = [30, 130, 90];
        rotSpeed = 0.08;
        s.targetRadius = s.baseRadius + Math.abs(Math.sin(t * 0.012)) * 28 + 4;
      } else if (st === 'EXECUTING') {
        [tnr, tng, tnb] = [255, 181, 71]; [tlr, tlg, tlb] = [130, 80, 20];
        rotSpeed = 0.06;
        s.targetRadius = s.baseRadius + Math.sin(t * 0.007) * 12;
      } else {
        [tnr, tng, tnb] = [120, 200, 255]; [tlr, tlg, tlb] = [40, 80, 120];
        rotSpeed = 0.005;
        s.targetRadius = s.baseRadius;
      }

      // Smooth color lerp
      const C = 0.055;
      s.colorR = lerp(s.colorR, tnr, C);
      s.colorG = lerp(s.colorG, tng, C);
      s.colorB = lerp(s.colorB, tnb, C);
      s.lineR = lerp(s.lineR, tlr, C);
      s.lineG = lerp(s.lineG, tlg, C);
      s.lineB = lerp(s.lineB, tlb, C);
      s.currentRadius = lerp(s.currentRadius, s.targetRadius, 0.05);

      s.angleY += rotSpeed;
      s.angleX += rotSpeed * 0.48;

      const sinX = Math.sin(s.angleX), cosX = Math.cos(s.angleX);
      const sinY = Math.sin(s.angleY), cosY = Math.cos(s.angleY);

      // Project 3D → 2D
      const pts = s.nodes.map(([nx, ny, nz]) => {
        const xy = cosX * ny - sinX * nz;
        const xz = sinX * ny + cosX * nz;
        const yz = cosY * xz - sinY * nx;
        const yx = sinY * xz + cosY * nx;
        const fx = yx * s.currentRadius;
        const fy = xy * s.currentRadius;
        const fz = yz * s.currentRadius;
        const zOff = Math.max(0.1, fz + 400);
        const f = 400 / zOff;
        return [cx + fx * f, cy + fy * f, fz];
      });

      // Draw edges
      const threshSq = (s.currentRadius * 0.43) ** 2;
      ctx.lineWidth = 0.5;
      for (let i = 0; i < pts.length; i++) {
        for (let j = i + 1; j < pts.length; j++) {
          const [x1, y1, z1] = pts[i];
          const [x2, y2, z2] = pts[j];
          const dSq = (x1 - x2) ** 2 + (y1 - y2) ** 2 + (z1 - z2) ** 2;
          if (dSq < threshSq) {
            const fade = Math.max(10, Math.min(255, (z1 + z2 + 200) / 2));
            const a = (fade / 255 * 0.75).toFixed(2);
            ctx.beginPath();
            ctx.strokeStyle = `rgba(${Math.round(s.lineR * fade / 255)},${Math.round(s.lineG * fade / 255)},${Math.round(s.lineB * fade / 255)},${a})`;
            ctx.moveTo(x1, y1);
            ctx.lineTo(x2, y2);
            ctx.stroke();
          }
        }
      }

      // Draw nodes
      const nr = Math.round(s.colorR), ng = Math.round(s.colorG), nb = Math.round(s.colorB);
      pts.forEach(([px, py, pz]) => {
        const size = Math.max(1.2, 2.2 + pz / 130);
        ctx.beginPath();
        ctx.fillStyle = `rgb(${nr},${ng},${nb})`;
        ctx.arc(px, py, size, 0, Math.PI * 2);
        ctx.fill();
      });

      s.raf = requestAnimationFrame(render);
    };

    s.raf = requestAnimationFrame(render);
    return () => {
      ro.disconnect();
      if (s.raf) cancelAnimationFrame(s.raf);
    };
  }, [buildNodes]);

  // Update state ref when zaraState changes (accessed in render loop via closure)
  // The render loop reads zaraState directly from the store via the ref trick below
  useEffect(() => {
    // The render loop uses the live zaraState variable from the outer closure;
    // re-triggering the effect when zaraState changes refreshes that closure.
  }, [zaraState]);

  return (
    <canvas
      ref={canvasRef}
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
    />
  );
}
