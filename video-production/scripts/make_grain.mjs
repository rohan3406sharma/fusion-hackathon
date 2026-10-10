// Deterministic film-grain tile (seeded LCG), used as a static, very low-opacity texture overlay.
import sharp from 'sharp'
import { fileURLToPath } from 'node:url'
const N = 512, buf = Buffer.alloc(N * N * 2)
let s = 20261009
const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296)
for (let i = 0; i < N * N; i++) { const g = Math.round(128 + (rnd() + rnd() + rnd() - 1.5) * 120); buf[i * 2] = Math.max(0, Math.min(255, g)); buf[i * 2 + 1] = 255 }
await sharp(buf, { raw: { width: N, height: N, channels: 2 } }).png().toFile(fileURLToPath(new URL('../assets/img/grain.png', import.meta.url)))
console.log('grain.png written')
