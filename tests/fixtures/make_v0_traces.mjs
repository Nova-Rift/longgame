// Golden traces from the Lifelong Arcade v0 TypeScript engine, so the Python port can be checked step for step.
// That engine lived in the author's website repository (src/arcade at commit fc7f4ed). To regenerate:
//   node --experimental-strip-types --no-warnings make_v0_traces.mjs /path/to/src/arcade > v0_traces.json
import {createHash} from 'node:crypto'
import {pathToFileURL} from 'node:url'
if(!process.argv[2])throw new Error('Pass the folder holding engine.ts, games.ts, run.ts and baseline.ts')
const base=pathToFileURL(process.argv[2].replace(/\/?$/,'/')).href
const {parseLevel,initialState,step,render,solve}=await import(base+'engine.ts')
const {RUN}=await import(base+'games.ts')
const {ArcadeRun}=await import(base+'run.ts')
const {mulberry32,randomBaseline,randomRun}=await import(base+'baseline.ts')
const canon=(grid,won)=>grid.map(r=>r.join(',')).join(';')+'|'+(won?1:0)
const h=s=>createHash('sha256').update(s).digest('hex').slice(0,16)
function trace(map,actions){const L=parseLevel(map);let s=initialState(L);const out=[h(canon(render(L,s),false))]
 for(const a of actions){const r=step(L,s,a);s=r.state;out.push(h(canon(render(L,s),r.won)))}return out}
const levels=[]
RUN.forEach((seg,si)=>seg.levels.forEach((lv,li)=>{
 const sol=solve(parseLevel(lv.map)),seqs=[]
 for(const [seed,n,k] of [[si*100+li+1,120,6],[si*100+li+51,250,5],[si*100+li+77,400,5]]){
  const rand=mulberry32(seed),actions=Array.from({length:n},()=>Math.floor(rand()*k));seqs.push({actions,hashes:trace(lv.map,actions)})}
 // solver path with random detours: walk the path, inserting a random action every third step
 const rand=mulberry32(9000+si*100+li),mixed=[];sol.path.forEach((a,i)=>{mixed.push(a);if(i%3===2)mixed.push(Math.floor(rand()*6))})
 seqs.push({actions:mixed,hashes:trace(lv.map,mixed)})
 levels.push({segment:si,level:li,game:seg.game,phase:seg.phase,par:lv.par,path:sol.path,solved_hash:trace(lv.map,sol.path).at(-1),seqs})
}))
const run1=randomRun(1)
const out={source:'Lifelong Arcade v0 TypeScript engine (website repository commit fc7f4ed, src/arcade: engine.ts, games.ts, run.ts, baseline.ts)',actions_v0:['up','right','down','left','use','restart'],
 canonical:"rows of ids joined by ',' and ';' + '|' + (won ? 1 : 0); sha256 hex[:16]",levels,
 random_run_seed1:{results:run1.results,score:run1.score(),history_length:run1.history.length},random_baseline_20:randomBaseline(20)}
process.stdout.write(JSON.stringify(out))
