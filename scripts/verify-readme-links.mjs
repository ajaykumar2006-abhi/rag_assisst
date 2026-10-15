import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const md = fs.readFileSync('README.md', 'utf8');
const re = /\[([^\]]+)\]\(([^)]+)\)/g;
let m;
let missed = 0;
let total = 0;

for (; (m = re.exec(md)); ) {
  const target = m[2].trim();
  if (target.includes('://')) continue;
  const frag = target.split('#')[0].replace(/\)\s*$/, '').trim();
  const p = path.resolve(root, frag.replace(/^\//, ''));
  total++;
  if (!fs.existsSync(p)) { missed++; console.log('MISSING', target); }
}

console.log('internal markdown file links checked:', missed === 0, '| scanned:', total, '| missing:', missed);
if (missed) process.exit(1);
