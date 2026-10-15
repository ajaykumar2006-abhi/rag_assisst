import { memo, useMemo } from "react";

/**
 * Layered CSS galaxy background.
 *
 * Stars are generated deterministically from a fixed seed so the layout never
 * shifts between renders, and they are drawn as two repeating raster-free
 * `radial-gradient` layers rather than hundreds of DOM nodes — cheap enough for a
 * CPU-only laptop. Every animation stops when motion is disabled.
 */
function makeStarLayer(count: number, size: number, seed: number): string {
  // Small deterministic PRNG (mulberry32) — stable across reloads.
  let state = seed;
  const random = () => {
    state |= 0;
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };

  const stars: string[] = [];
  const spread = 1000;
  for (let index = 0; index < count; index += 1) {
    const x = Math.round(random() * spread);
    const y = Math.round(random() * spread);
    const alpha = (0.35 + random() * 0.6).toFixed(2);
    stars.push(`radial-gradient(${size}px ${size}px at ${x}px ${y}px, rgba(255,255,255,${alpha}), transparent 100%)`);
  }
  return stars.join(",");
}

export const GalaxyBackground = memo(function GalaxyBackground({ motionEnabled }: { motionEnabled: boolean }) {
  const far = useMemo(() => makeStarLayer(90, 1, 1337), []);
  const near = useMemo(() => makeStarLayer(45, 1.6, 90210), []);

  return (
    <div className={`galaxy${motionEnabled ? "" : " galaxy--static"}`} aria-hidden="true">
      <div className="galaxy__nebula galaxy__nebula--one" />
      <div className="galaxy__nebula galaxy__nebula--two" />
      <div
        className="galaxy__stars--far"
        style={{ backgroundImage: far, backgroundSize: "1000px 1000px" }}
      />
      <div
        className="galaxy__stars--near"
        style={{ backgroundImage: near, backgroundSize: "1000px 1000px", backgroundPosition: "140px 220px" }}
      />
    </div>
  );
});
