import React, { useRef, useEffect, useCallback } from 'react';
import { useZaraStore } from '../store/zaraStore';

// ─── Exact colour targets from ui_engine.py ───────────────────────────────────
const STATE_COLORS = {
  STANDBY:   { node: [0,   80,  255], line: [0,   40,  127], rotSpeed: 0.005 },
  LISTENING: { node: [255, 40,  40 ], line: [150, 20,  20 ], rotSpeed: 0.020 },
  THINKING:  { node: [0,   212, 255], line: [0,   80,  160], rotSpeed: 0.080 },
  TALKING:   { node: [100, 255, 220], line: [30,  120, 100], rotSpeed: 0.080 },
  EXECUTING: { node: [255, 181, 71 ], line: [120, 80,  20 ], rotSpeed: 0.040 },
};
const DEFAULT_COLORS = STATE_COLORS.STANDBY;

const NUM_NODES  = 120;
const BASE_RADIUS = 200;
const COLOR_LERP  = 0.06;   // same as pygame
const RADIUS_LERP = 0.05;   // same as pygame

// ─── Build Fibonacci sphere once ────────────────────────────────────────────
function buildFibonacciSphere(n) {
  const phi = Math.PI * (3 - Math.sqrt(5));
  const nodes = [];
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const theta = phi * i;
    nodes.push([Math.cos(theta) * r, y, Math.sin(theta) * r]);
  }
  return nodes;
}

const NODES = buildFibonacciSphere(NUM_NODES);

export default function NeuralSphere() {
  const canvasRef = useRef(null);
  const stateRef  = useRef({
    angleX: 0, angleY: 0,
    currentRadius: BASE_RADIUS, targetRadius: BASE_RADIUS,
    nodeR: 0, nodeG: 80, nodeB: 255,
    lineR: 0, lineG: 40, lineB: 127,
    rafId: null,
  });

  const zaraState  = useZaraStore(s => s.zaraState);
  const zaraStateRef = useRef(zaraState);
  useEffect(() => { zaraStateRef.current = zaraState; }, [zaraState]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx    = canvas.getContext('2d');
    const W      = canvas.width;
    const H      = canvas.height;
    const s      = stateRef.current;
    const state  = zaraStateRef.current;
    const now    = performance.now() / 1000;
    const colors = STATE_COLORS[state] || DEFAULT_COLORS;

    // ── Rotation speed & radius target ───────────────────────────────────────
    const rotSpeed = colors.rotSpeed;
    if (state === 'LISTENING') {
      const heartbeat = (Math.sin(now * 8) + 1) / 2;
      s.targetRadius = BASE_RADIUS + heartbeat * 30;
    } else if (state === 'TALKING') {
      const voicePulse = (Math.sin(now * 6) + 1) / 2 * 25;
      s.targetRadius = BASE_RADIUS + voicePulse;
    } else {
      s.targetRadius = BASE_RADIUS + Math.sin(now * 1) * 5;
    }

    // ── Lerp color ────────────────────────────────────────────────────────────
    const [tnr, tng, tnb] = colors.node;
    const [tlr, tlg, tlb] = colors.line;
    s.nodeR += (tnr - s.nodeR) * COLOR_LERP;
    s.nodeG += (tng - s.nodeG) * COLOR_LERP;
    s.nodeB += (tnb - s.nodeB) * COLOR_LERP;
    s.lineR += (tlr - s.lineR) * COLOR_LERP;
    s.lineG += (tlg - s.lineG) * COLOR_LERP;
    s.lineB += (tlb - s.lineB) * COLOR_LERP;

    // ── Lerp radius + rotate ──────────────────────────────────────────────────
    s.currentRadius += (s.targetRadius - s.currentRadius) * RADIUS_LERP;
    s.angleY += rotSpeed;
    s.angleX += rotSpeed * 0.5;

    const sinX = Math.sin(s.angleX), cosX = Math.cos(s.angleX);
    const sinY = Math.sin(s.angleY), cosY = Math.cos(s.angleY);

    // ── Project nodes ─────────────────────────────────────────────────────────
    const projected = NODES.map(([x, y, z]) => {
      // Rotation X
      const xy = cosX * y - sinX * z;
      const xz = sinX * y + cosX * z;
      // Rotation Y
      const yz = cosY * xz - sinY * x;
      const yx = sinY * xz + cosY * x;

      const fx = yx * s.currentRadius;
      const fy = xy * s.currentRadius;
      const fz = yz * s.currentRadius;

      const zOff = Math.max(0.1, fz + 400);
      const fac  = 400 / zOff;

      return [
        W / 2 + fx * fac,
        H / 2 + fy * fac,
        fz,
      ];
    });

    // ── Clear ─────────────────────────────────────────────────────────────────
    ctx.fillStyle = '#0a0c10';
    ctx.fillRect(0, 0, W, H);

    // ── Draw connections ──────────────────────────────────────────────────────
    const threshSq = (s.currentRadius * 0.45) ** 2;
    const lr = s.lineR | 0, lg = s.lineG | 0, lb = s.lineB | 0;
    for (let i = 0; i < projected.length; i++) {
      const [px, py, pz] = projected[i];
      for (let j = i + 1; j < projected.length; j++) {
        const [qx, qy, qz] = projected[j];
        const dx = px - qx, dy = py - qy, dz = pz - qz;
        const distSq = dx*dx + dy*dy + dz*dz;
        if (distSq < threshSq) {
          const depthFade = Math.max(10, Math.min(255, ((pz + qz + 200) / 2) | 0));
          const f = depthFade / 255;
          ctx.strokeStyle = `rgb(${(lr*f)|0},${(lg*f)|0},${(lb*f)|0})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(px, py);
          ctx.lineTo(qx, qy);
          ctx.stroke();
        }
      }
    }

    // ── Draw nodes ─────────────────────────────────────────────────────────────
    const nr = s.nodeR | 0, ng = s.nodeG | 0, nb = s.nodeB | 0;
    ctx.fillStyle = `rgb(${nr},${ng},${nb})`;
    for (const [px, py, pz] of projected) {
      const size = Math.max(1, 3 + pz / 100);
      ctx.beginPath();
      ctx.arc(px, py, size, 0, Math.PI * 2);
      ctx.fill();
    }

    s.rafId = requestAnimationFrame(draw);
  }, []);

  // ── Resize canvas to fill parent ────────────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ro = new ResizeObserver(() => {
      canvas.width  = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    });
    ro.observe(canvas);
    canvas.width  = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;
    return () => ro.disconnect();
  }, []);

  // ── Start / stop RAF ────────────────────────────────────────────────────────
  useEffect(() => {
    stateRef.current.rafId = requestAnimationFrame(draw);
    return () => {
      if (stateRef.current.rafId) cancelAnimationFrame(stateRef.current.rafId);
    };
  }, [draw]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: '100%', height: '100%', display: 'block' }}
    />
  );
}
