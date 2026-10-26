/* Actual DSH services/factory, isolated home and synthetic workspaces, no model.
 * Args: DSH_NODE_MODULES PERSISTENT_PYTHON NEW_OUTPUT_UNDER_DIST
 * ASAR installations must use Desktop's Electron Node mode; ordinary installs use Node.
 */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const cp = require('node:child_process');
const { syncBuiltinESMExports } = require('node:module');
const { pathToFileURL } = require('node:url');
const [modules, python, output] = process.argv.slice(2);
const checkout = path.resolve(__dirname, '../..');
const base = path.resolve(output || '.');
assert(base.startsWith(path.join(checkout, 'dist') + path.sep) && !fs.existsSync(base));
fs.mkdirSync(base, { recursive: true });
process.env.DSH_HOME = path.join(base, 'home');
const launches = [];
const spawn = cp.spawn;
cp.spawn = function(command, args, options) {
  const child = spawn.call(this, command, args, options);
  if (Array.isArray(args) && args.includes('math_research.mcp.server')) {
    launches.push({ child, pid: child.pid, cwd: options.cwd, args });
  }
  return child;
};
syncBuiltinESMExports();
const load = name => import(pathToFileURL(path.join(modules, '@deepseek-ai', name, 'lib/index.js')).href);
const report = { cases: {}, model_called: false };
function record(name, facts) {
  report.cases[name] = { passed: true, ...facts };
  fs.writeFileSync(path.join(base, 'acceptance.json'), JSON.stringify(report, null, 2));
  console.log(name, JSON.stringify(facts));
}
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function gone(list) {
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    if (list.every(p => p.child.exitCode !== null || p.child.signalCode !== null)) return;
    await sleep(50);
  }
  assert.fail('MCP transport/process did not exit after Agent disposal');
}

(async () => {
  const versions = ['dsh-agent', 'dsh-mcp-client'].map(n => JSON.parse(fs.readFileSync(path.join(modules, '@deepseek-ai', n, 'package.json'))).version);
  assert(versions.every(v => v === '0.2.1-rc.3'));
  report.dsh = versions[0];
  const roots = ['workspace-A', 'workspace-B', 'empty-workspace'].map(n => path.join(base, n));
  roots.forEach(p => fs.mkdirSync(p));
  const seed = cp.spawnSync(python, ['-I', '-B', '-c',
    "import sys;from pathlib import Path;from math_research.core.workspace import init_workspace;from math_research.services.research import create_problem;[(init_workspace(Path(p)),create_problem(Path(p)/'.math-research-ledger','SYNTHETIC_'+Path(p).name)) for p in sys.argv[1:]]",
    ...roots.slice(0,2)], { cwd: checkout, encoding: 'utf8', timeout: 20000 });
  assert.equal(seed.status, 0, seed.stderr);
  const [a,b,empty] = roots;
  fs.mkdirSync(path.join(a, 'subdir'));
  const {Context} = await load('cordis');
  let ctx = new Context();
  const handles = [];
  let host;
  let serial = 0;
  const names = agent => ctx.tools.schemas(agent).map(t => t.name).filter(n => n.startsWith('mcp__math-research-ledger__')).sort();
  const create = async root => {
    const handle = await ctx.agents.create({ sessionId: 'fixture-'+(++serial), meta: root ? {cwd:root} : {}, agentOptions:{provider:'no-network',model:'fixture'} });
    handles.push(handle);
    return handle;
  };
  const call = async (handle, tool='research_status', args={}) => {
    const r = await ctx.tools.execute({callId:'fixture-'+(++serial),name:'mcp__math-research-ledger__'+tool,arguments:args,agent:handle.agent,signal:new AbortController().signal});
    if (r.value?.structuredContent) return r.value.structuredContent;
    // DSH promotes MCP isError into its ToolResult error channel.
    if (r.isError && r.error?.message) {
      const payload=JSON.parse(r.error.message);
      assert(payload.error?.code, 'Expected a structured MCP failure');
      return payload;
    }
    assert.fail('Tool execution failed without a structured result');
  };
  const check = async (handle, root) => {
    assert.equal(names(handle.agent).length,11);
    const r = await call(handle); assert.equal(path.resolve(r.workspace_root),path.resolve(root));return r;
  };
  const plugin=require('./host-plugin/index.cjs');
  async function boot() {
    for (const n of ['dsh-session','dsh-agent','dsh-llm','dsh-system-prompt','dsh-tools','dsh-session-projection','dsh-subprocess-local']) await ctx.plugin((await load(n)).default,{});
    const persistence=await load('dsh-session-persistence-jsonl');
    await ctx.plugin(persistence,{root:path.join(base,'sessions'),compression:'none'});
    await ctx.plugin((await load('dsh-agent-loop')).default,{agents:[],maxParallelToolCalls:10});
    host=await ctx.plugin(plugin,{python});
  }
  try {
    await boot();
    const ha=await create(a), hb=await create(b);
    const sa=await check(ha,a),sb=await check(hb,b);
    assert(!JSON.stringify(sa).includes('SYNTHETIC_workspace-B') && !JSON.stringify(sb).includes('SYNTHETIC_workspace-A'));
    for (const [h,other] of [[ha,b],[hb,a]]) assert.equal((await call(h,'research_status',{workspace:other})).error.code,'WORKSPACE_OUT_OF_SCOPE');
    const live=launches.filter(p=>p.child.exitCode===null && p.child.signalCode===null);
    assert.equal(live.length,2,JSON.stringify(launches.map(p=>({pid:p.pid,cwd:p.cwd,exit:p.child.exitCode}))));
    assert.notEqual(live[0].pid,live[1].pid);
    record('different_workspace_concurrent',{tools:[11,11],pids:live.map(p=>p.pid),startup_processes:launches.length,cross_root_rejected:true});
    record('agent_create',{registered_before_create_return:true});
    // Enter the actual driver's first request boundary, then stop before provider I/O.
    let gate=false;
    const unhook=ha.agent.ctx.on('agent/request',async()=>{
      assert.equal(names(ha.agent).length,11);gate=true;throw new Error('SYNTHETIC_NO_MODEL_GATE');
    });
    ha.agent.followup({content:[{type:'text',text:'Synthetic readiness fixture; no research.'}],source:{kind:'test'}});
    await ha.agent.whenIdle();
    unhook();assert(gate,'Agent did not reach the first-request gate');
    record('first_turn_availability',{tools:11,provider_called:false});
    const ha2=await create(a);await check(ha2,a);
    const sameRootProcesses=launches.filter(p=>p.cwd===a && p.child.exitCode===null && p.child.signalCode===null);
    assert.equal(sameRootProcesses.length,2);
    const generation=path.join(a,'.math-research-ledger/.checkpoint-generation');
    const before=fs.existsSync(generation)?fs.readFileSync(generation,'utf8'):null;
    const writes=await Promise.all([ha,ha2].map((h,i)=>call(h,'research_create_problem',{title:'WRITER_'+i,statement:'Synthetic fixture only.',primary_target:'Concurrency fixture.'})));
    assert.equal(new Set(writes.map(r=>r.problem_id)).size,2);
    assert.deepEqual(await check(ha,a),await check(ha2,a));
    assert.equal((await call(ha)).problems,3);
    assert.notEqual(fs.readFileSync(generation,'utf8'),before);
    assert(!fs.existsSync(path.join(a,'.math-research-ledger/.checkpoint.lock')));
    assert.deepEqual(await call(ha,'research_search',{query:'WRITER_0',limit:1}),await call(ha2,'research_search',{query:'WRITER_0',limit:1}));
    record('same_workspace_concurrent',{tools:[11,11],processes:2,problems:3,search_equal:true,generation_changed:true,lock_released:true});
    for(const [label,root] of [['ordinary_subdirectory',path.join(a,'subdir')],['state_directory_exact_root',path.join(a,'.math-research-ledger')],['uninitialized',empty]]) {
      const h=await create(root);assert.equal(names(h.agent).length,11);
      assert.equal((await call(h)).error.code,'NO_WORKSPACE');
      assert(!fs.existsSync(path.join(root,'.math-research-ledger')));
      record(label,{tools:11,error:'NO_WORKSPACE',auto_init:false});
    }
    const localShell=await load(process.platform==='win32'?'dsh-pwsh-local':'dsh-bash-local');
    await ha.agent.ctx.plugin(localShell.default??localShell,{cwd:a});
    const quoted=b.replaceAll("'","''");
    const command=process.platform==='win32'?`Set-Location -LiteralPath '${quoted}'; (Get-Location).Path`:`cd '${b.replaceAll("'","'\\''")}' && pwd`;
    let shellResult;
    const shellScope=await ha.agent.ctx.inject(['shell'],async shellCtx=>{
      const execution=await shellCtx.shell.execute(shellCtx.shell.resolve({command,cwd:a,timeoutMs:10000}));
      shellResult=await execution.result();
    });
    await shellScope.dispose();
    assert.equal(shellResult.exitCode,0);assert(shellResult.stdout.text.includes(b));
    const cwd=process.cwd();process.chdir(b);await check(ha,a);process.chdir(cwd);
    record('shell_cd_immutability',{root_unchanged:true,method:'official Agent-local shell cd plus Host process cwd change'});
    const first=live.find(p=>p.cwd===a);assert(first);await ha.dispose();await gone([first]);
    record('agent_dispose',{process_exited:true});
    process.chdir(b);
    const resumed=await ctx.agents.resume({resumeSessionId:ha.agent.id,agentOptions:{provider:'no-network',model:'fixture'}});
    handles.push(resumed);await check(resumed,a);process.chdir(cwd);
    record('resume',{restored_header_root:'workspace-A',host_cwd_was:'workspace-B',new_pid:launches.at(-1).pid});
    await host.dispose();
    const off=await create(b);assert.equal(names(off.agent).length,0);
    assert.equal(names(hb.agent).length,11);
    record('profile_plugin_OFF',{new_agent_tools:0,existing_agent_tools:11,semantics:'normal Cordis plugin-entry unload; existing agent scopes retained'});
    host=await ctx.plugin(plugin,{python});
    const on=await create(b);await check(on,b);
    record('profile_plugin_ON',{new_agent_tools:11});
    await on.dispose();const restarted=await create(b);await check(restarted,b);
    record('restart',{fresh_agent:true,tools:11,new_pid:launches.at(-1).pid});
    const count=launches.length;
    await assert.rejects(create(undefined),/NO_WORKSPACE/);
    assert.equal(launches.length,count);
    record('missing_host_root',{failed_closed:true,process_spawned:false});
    for(const h of handles.reverse()) await h.dispose();
    handles.length=0;
    await host.dispose();await ctx.fiber.dispose();await gone(launches);
    ctx=new Context();await boot();
    const afterRestart=await ctx.agents.resume({resumeSessionId:ha.agent.id,agentOptions:{provider:'no-network',model:'fixture'}});
    handles.push(afterRestart);await check(afterRestart,a);
    record('restart',{fresh_host_context:true,persisted_root:'workspace-A',tools:11,new_pid:launches.at(-1).pid});
  } finally {
    for(const h of handles.reverse()) await h.dispose();
    if(host) await host.dispose();
    await ctx.fiber.dispose();
    await gone(launches);
    report.launches=launches.map(({pid,cwd,args})=>({pid,cwd,args}));
    fs.writeFileSync(path.join(base,'acceptance.json'),JSON.stringify(report,null,2));
  }
})().catch(error=>{console.error(error.stack);process.exitCode=1});
