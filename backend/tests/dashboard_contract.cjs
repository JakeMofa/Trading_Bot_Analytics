// Exercise the shipped script against actual FastAPI fixture responses without a browser dependency.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const fixture = JSON.parse(fs.readFileSync(0, 'utf8'));
const nodes = new Map();
function node() {
  return {textContent:'',style:{},dataset:{},children:[],clientWidth:800,
    append(...children){this.children.push(...children);},
    replaceChildren(...children){this.children=children;},
    setAttribute(){},addEventListener(){},showModal(){},close(){},
    getContext(){return new Proxy({createLinearGradient(){return {addColorStop(){}};},measureText(){return {width:60};}}, {get(target,key){return target[key] || (()=>{});}});}};
}
const paths = [];
const stream = [];
const context = vm.createContext({
  console,URL,Date,Math,Number,String,Object,JSON,Promise,Error,
  document:{getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);},createElement:node,createElementNS:node,querySelectorAll(){return [];}},
  window:{devicePixelRatio:1,addEventListener(){},EventSource:true},
  location:{protocol:'http:'},performance:{now:()=>100},
  requestAnimationFrame(callback){callback();}, setInterval(){},clearInterval(){},
  EventSource:class {constructor(path){paths.push(path);stream.push(this);}},
  fetch:async path=>{paths.push(path);return {ok:true,status:200,json:async()=>structuredClone(fixture[path] || {}),text:async()=>''};},
});
const html = fs.readFileSync(process.argv[2],'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
vm.runInContext(script,context);
(async()=>{
  await new Promise(setImmediate);
  assert.match(nodes.get('live-reference').textContent,/101/);
  assert.match(nodes.get('market-up').textContent,/55/);
  assert.equal(stream.length,1);
  assert(paths.includes('/events'));
  const incoming=structuredClone(fixture['/state/current']);
  incoming.coinbase.price_usd=102;
  stream[0].onmessage({data:JSON.stringify(incoming)});
  assert.match(nodes.get('live-reference').textContent,/102/);
  assert.match(nodes.get('forecast-up').textContent,/UP/);
  vm.runInContext("showPage('system')",context);
  await new Promise(setImmediate);
  assert(nodes.get('system-status').children.length>10);
  assert(nodes.get('system-charts').children.length>0);
  assert(paths.every(path=>!path.startsWith('/api/')));
  console.log('FastAPI fixtures rendered; SSE updates, history, and system charts passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
