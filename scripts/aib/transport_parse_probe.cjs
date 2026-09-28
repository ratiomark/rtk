// Warm consumer cost, after RTK exits. JSON stdout is already in memory;
// file mode must read its evidence file. Neither test includes trace persistence.
const fs = require('node:fs');
const path = require('node:path');
const { performance } = require('node:perf_hooks');

const directory = process.argv[2];
const results = [];
for (const name of fs.readdirSync(directory)) {
  if (!/^(small|large)-.*\.json-stdout\.json$/.test(name)) continue;
  const caseName = name.replace('.json-stdout.json', '');
  const jsonBytes = fs.readFileSync(path.join(directory, name));
  const evidencePath = path.join(directory, `${caseName}.evidence.json`);
  const stdoutBytes = fs.readFileSync(path.join(directory, `${caseName}.stdout.txt`));
  const samples = { json: [], file: [] };
  let consumed = 0;
  for (let iteration = 0; iteration < 110; iteration++) {
    const order = iteration % 2 ? ['file', 'json'] : ['json', 'file'];
    for (const mode of order) {
      const start = performance.now();
      const envelope = mode === 'json'
        ? JSON.parse(jsonBytes.toString('utf8'))
        : {
            ...JSON.parse(fs.readFileSync(evidencePath, 'utf8')),
            stdout: stdoutBytes.toString('utf8'),
          };
      consumed += envelope.stdout.length;
      const elapsed = performance.now() - start;
      if (iteration >= 10) samples[mode].push(elapsed);
    }
  }
  const entry = { name: caseName, consumed, modes: {} };
  for (const [mode, values] of Object.entries(samples)) {
    values.sort((a, b) => a - b);
    entry.modes[mode] = { medianMs: values[50], p90Ms: values[90] };
  }
  results.push(entry);
}
fs.writeFileSync(path.join(directory, 'parse-results.json'), JSON.stringify(results, null, 2));
console.log(JSON.stringify(results.map(({ consumed, ...result }) => result), null, 2));
