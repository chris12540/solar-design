// Expose the captured module runtime without starting the account application.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const parser=require('/Users/chris/code/solar-designer/frontend/node_modules/@babel/parser');
const root=path.join(__dirname,'runtime','frontend');
const source=fs.readFileSync(path.join(root,'frontend.0.14683.9.js'),'utf8');
const expected='42976d01ffe5ecd1b87b9e083b645944c88d42d4010c69ea8fdb4a56e3b9194f';
if(crypto.createHash('sha256').update(source).digest('hex')!==expected)throw Error('Bootstrap identity mismatch');
const ast=parser.parse(source,{sourceType:'script'});
const body=ast.program.body[0].expression.callee.body.body;
const entry=body.find(node=>node.type==='VariableDeclaration'&&node.declarations.some(d=>d.id.name==='n'&&d.init?.type==='CallExpression'&&d.init.arguments[0]?.value==='./node_modules/@datadog/browser-rum/esm/entries/main.js'));
if(!entry)throw Error('Unknown bootstrap layout; refusing to instrument');
const derived=source.slice(0,entry.start)+'window.__auroraFrontendRequire=r;r.p="/frontend-assets/";delete r.f.prefetch;r.F={};})();\n';
fs.writeFileSync(path.join(root,'frontend-runtime.js'),derived,{mode:0o600});
const manifest={};
for(const file of ['frontend-runtime.js','local-roof-ui.js']){
 const data=fs.readFileSync(path.join(root,file));
 manifest[file]={bytes:data.length,sha256:crypto.createHash('sha256').update(data).digest('hex'),derived:true};
}
fs.writeFileSync(path.join(root,'derived-manifest.json'),JSON.stringify(manifest,null,2),{mode:0o600});
fs.writeFileSync(path.join(root,'runtime-provenance.json'),JSON.stringify({sourceSha256:expected,preservedPrefixEndCharacter:entry.start,change:'Expose module loader; do not invoke whole-application startup, telemetry, or speculative prefetch. Component and provider functions are unchanged.',derivedSha256:manifest['frontend-runtime.js'].sha256},null,2),{mode:0o600});
console.log('Derived component-only runtime:',derived.length,'characters');
