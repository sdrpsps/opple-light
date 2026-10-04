import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';

async function check(directory) {
  let count = 0;
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const file = join(directory, entry.name);
    if (entry.isDirectory()) count += await check(file);
    else if (/\.[cm]?jsx?$/.test(file)) {
      throw new Error(`${file}: frontend source must use TypeScript`);
    } else if (file.endsWith('.vue')) {
      const source = await readFile(file, 'utf8');
      if (/<script\b/.test(source) && !/<script\b[^>]*lang=["']ts["']/.test(source))
        throw new Error(`${file}: Vue scripts must use lang="ts"`);
      const lines = source.trimEnd().split('\n').length;
      if (lines > 250)
        throw new Error(`${file}: ${lines} lines exceeds the 250-line component limit`);
      count++;
      console.log(`${file}: ${lines}/250 lines`);
    }
  }
  return count;
}
console.log(`Checked ${await check('frontend/src')} Vue components.`);
