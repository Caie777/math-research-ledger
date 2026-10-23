/* Boot the real installed DSH Desktop Host profile. No model, auth inspection or writes
 * to Ledger. Optional --cycle uses the official PluginManager's persisted ON/OFF.
 * Arguments: DSH_NODE_MODULES PROFILE_DIR WORKSPACE REPORT [--cycle]
 */
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const childProcess = require('node:child_process');
const { syncBuiltinESMExports } = require('node:module');

// Observe only this MCP server's launch command, never unrelated arguments or env.
// This proves which interpreter the actual official bridge spawned.
const ledgerProcesses = [];
const originalSpawn = childProcess.spawn;
childProcess.spawn = function(command, args, ...options) {
  const child = originalSpawn.call(this, command, args, ...options);
  if (Array.isArray(args) && args.includes('math_research.mcp.server')) {
    ledgerProcesses.push({ executable: String(command), pid: child.pid });
  }
  return child;
};
syncBuiltinESMExports();

(async () => {
  const [modules, profileDir, workspace, reportPath, cycle] = process.argv.slice(2);
  if (!modules || !profileDir || !workspace || !reportPath) {
    throw new Error('Arguments: DSH_NODE_MODULES PROFILE_DIR WORKSPACE REPORT [--cycle]');
  }
  const load = relative => import(pathToFileURL(path.join(modules, relative)).href);
  const { runProfile } = await load('@deepseek-ai/dsh/lib/profile-boot.js');
  const { loadProfileDirectory, loadLayeredEnv } = await load('@deepseek-ai/dsh-app-boot/lib/index.js');
  const installAnchor = path.join(modules, '@deepseek-ai/dsh/package.json');
  const profile = loadProfileDirectory('dsh', path.resolve(profileDir), installAnchor);
  const runtime = await runProfile({ environment: loadLayeredEnv('dsh'),
    profile: path.basename(profileDir), resolvedProfile: { profile, installAnchor },
    patchFiles: [], args: ['--no-open', '--host', '127.0.0.1', '--port', '0'] });
  const names = () => runtime.ctx.tools.schemas().map(t => t.name)
    .filter(n => n.startsWith('mcp__math-research-ledger__')).sort();
  try {
    const report = { profile: path.basename(profileDir), model_called: false, tools_before: names() };
    if (report.tools_before.length !== 9) {
      throw new Error(`Initial ON expected 9 tools, found ${report.tools_before.length}`);
    }
    if (cycle === '--cycle') {
      report.off = await runtime.ctx.pluginManager.setBundleEnabled('dsh-math-research-ledger', false);
      report.off_tools = names();
      if (report.off_tools.length) throw new Error('OFF still exposes Ledger tools');
      report.on = await runtime.ctx.pluginManager.setBundleEnabled('dsh-math-research-ledger', true);
    }
    report.tools = names();
    if (report.tools.length !== 9) throw new Error(`Expected 9 tools, found ${report.tools.length}`);
    const call = async (tool, args) => {
      const value = await runtime.ctx.tools.execute({ callId: `ledger-readonly-${tool}`,
        name: `mcp__math-research-ledger__${tool}`, arguments: { workspace, ...args },
        signal: new AbortController().signal });
      if (value.isError || value.value?.isError || !value.value?.structuredContent) {
        throw new Error(`Read-only tool failed: ${JSON.stringify(value).slice(0, 1200)}`);
      }
      return value.value.structuredContent;
    };
    report.status = await call('research_status', {});
    report.search = await call('research_search', { query: 'PROBLEM-0001', limit: 1 });
    report.ledger_processes = ledgerProcesses;
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
    console.log(JSON.stringify({ profile: report.profile, initial_tool_count: report.tools_before.length,
      tool_count: report.tools.length, mcp_process_count: ledgerProcesses.length,
      off_tool_count: report.off_tools?.length, workspace: report.status.workspace_root,
      problems: report.status.problems, objects: report.status.objects,
      search_refs: report.search.hits.map(h => h.ref), model_called: false }));
  } finally { await runtime.shutdown.shutdown(0); }
})().catch(error => { console.error(error.stack || error); process.exitCode = 1; });
