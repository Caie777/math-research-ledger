/* Real installed DSH profile/ToolRuntime smoke, without a model or chat history.
 * Run with the installed Desktop Electron in Node mode (--expose-internals),
 * or Node with the installed DSH module tree. All writes target a synthetic ledger.
 */
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

(async () => {
  const [moduleRoot, ledgerPatch, probePatch, reportPath, mode = 'read'] = process.argv.slice(2);
  if (!moduleRoot || !ledgerPatch || !probePatch || !reportPath) {
    throw new Error('Arguments: DSH_NODE_MODULES ledger.patch.yml probe.patch.yml report.json [write]');
  }
  const { runProfile } = await import(pathToFileURL(path.join(moduleRoot, '@deepseek-ai/dsh/lib/profile-boot.js')).href);
  const runtime = await runProfile({ environment: { get: name => process.env[name] }, profile: 'headless',
    patchFiles: [ledgerPatch, probePatch], args: [] });
  try {
    const tools = runtime.ctx.tools;
    const names = tools.schemas().map(x => x.name).filter(x => x.startsWith('mcp__math-research-ledger__'));
    if (names.length !== 11) throw new Error(`Expected 11 Ledger tools; found ${names.length}`);
    let seq = 0;
    const call = async (tool, args) => {
      const result = await tools.execute({ callId: `ledger-probe-${++seq}`,
        name: `mcp__math-research-ledger__${tool}`, arguments: args,
        signal: new AbortController().signal });
      if (result.isError) throw new Error(JSON.stringify(result));
      const payload = result.value?.structuredContent;
      if (!payload) throw new Error(`Missing structured MCP payload: ${JSON.stringify(result).slice(0, 1200)}`);
      return payload;
    };
    const status = await call('research_status', {});
    if (status.workspace_root !== process.cwd()) throw new Error('DSH cwd discovery bound the wrong workspace');
    const packet = await call('research_context_packet', { ref: 'PROBLEM-0001:problem:PROBLEM-0001', token_budget: 6000 });
    const search = await call('research_search', { query: 'LEDGER-CONTINUITY-A', problem_id: 'PROBLEM-0001' });
    const marker = search.hits.find(h => h.ref?.kind === 'claim' || (typeof h.ref === 'string' && h.ref.includes(':claim:')));
    if (!marker) throw new Error('Codex checkpoint A marker not recovered through Ledger');
    const ref = typeof marker.ref === 'string' ? marker.ref : `${marker.ref.problem_id}:${marker.ref.kind}:${marker.ref.object_id}`;
    const object = await call('research_get_object', { ref, length: 8000 });
    if (!object.content.includes('LEDGER-CONTINUITY-A')) throw new Error('Marker A body missing');
    const report = { harness: 'DeepSeek Harness', tools: names, marker_a: {
      ref, version: object.version, provenance: object.provenance,
      freshness: object.freshness, authority: object.authority },
      packet_source_version: packet.source_version, model_called: false };
    if (mode === 'write') {
      const id = ref.split(':').at(-1);
      report.episode_b = await call('research_ingest_episode', {
        problem_id: 'PROBLEM-0001', provenance: 'synthetic DeepSeek ToolRuntime session B',
        markdown: '# Confirmed Research Increment\n\n## Gap: Synthetic continuity B\nUses: ' + id +
          '\n\nLEDGER-CONTINUITY-B. Synthetic unresolved engineering checkpoint referencing marker A.\n\n' +
          '# Next Research Directions\n\nAdvisory: recover both checkpoints in a fresh Codex session.\n' });
    }
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
    console.log(JSON.stringify({ tool_count: names.length, recovered_a: ref, model_called: false,
      episode_b: report.episode_b?.episode_id }));
  } finally {
    await runtime.shutdown.shutdown(0);
  }
})().catch(error => { console.error(error.stack || error); process.exitCode = 1; });
