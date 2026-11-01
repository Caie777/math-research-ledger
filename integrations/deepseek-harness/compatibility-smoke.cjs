// Tiny packaging check: use the same prerelease option as DSH's compatibility gate.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const { pathToFileURL } = require('node:url');
const modules = process.argv[2] || process.env.MRL_DSH_NODE_MODULES;
assert(modules, 'Pass the installed DSH node_modules directory');
const anchor = path.join(modules, '@deepseek-ai/dsh-app-boot/package.json');
const semver = createRequire(anchor)('semver');
const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, 'host-plugin/package.json'), 'utf8'));
const ranges = [manifest.engines.dsh, manifest.peerDependencies['@deepseek-ai/dsh-agent'], manifest.peerDependencies['@deepseek-ai/dsh-mcp-client']];
assert.deepEqual(ranges, ['0.2.x', '0.2.x', '0.2.x']);
const cases = {'0.2.1-rc.3': true, '0.2.1-rc.5': true, '0.2.1': true, '0.2.2-rc.1': true, '0.2.9': true, '0.3.0-rc.1': false, '0.3.0': false};
(async () => {
  const { evaluatePluginCompatibility, getDshRuntimeVersion } = await import(pathToFileURL(path.join(path.dirname(anchor), 'lib/index.js')).href);
  for (const [version, expected] of Object.entries(cases)) {
    for (const range of ranges) assert.equal(semver.satisfies(version, range, {includePrerelease: true}), expected, version);
    assert.equal(evaluatePluginCompatibility(manifest, {}, version) === undefined, expected, version);
    const peersOnly = {...manifest}; delete peersOnly.engines;
    assert.equal(evaluatePluginCompatibility(peersOnly, {}, version) === undefined, expected, version);
  }
  assert.equal(evaluatePluginCompatibility(manifest), undefined);
  console.log(JSON.stringify({range: ranges[0], includePrerelease: true, runtime: getDshRuntimeVersion(), cases, currentCompatibleWithoutExemption: true}, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
