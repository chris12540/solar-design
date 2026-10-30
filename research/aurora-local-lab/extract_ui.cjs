// Derive a component-only module from captured source, preserving its functions.
// The enclosing application route and its startup are not executed or patched.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const parser=require('/Users/chris/code/solar-designer/frontend/node_modules/@babel/parser');
const traverse=require('/Users/chris/code/solar-designer/frontend/node_modules/@babel/traverse').default;
const generate=require('/Users/chris/code/solar-designer/frontend/node_modules/@babel/generator').default;
const root=path.join(__dirname,'runtime','frontend');
const index=JSON.parse(fs.readFileSync(path.join(root,'module-index.json'),'utf8'));
function derive(moduleId,exportsMap,derivedId){
const info=index[moduleId],source=fs.readFileSync(path.join(root,info.file),'utf8');
const ast=parser.parse('({'+source.slice(info.start,info.end)+'})');
let factory;
traverse(ast,{ObjectMethod(p){if(!factory)factory=p;}});
const scope=factory.scope;
const names=new Set(),declarations=new Map(),kinds=new Map();
function dependenciesOf(p){
  p.traverse({ReferencedIdentifier(ref){
    const dependency=ref.scope.getBinding(ref.node.name);
    if(dependency?.scope===scope)add(ref.node.name);
  }});
}
function add(name){
  if(names.has(name))return;
  names.add(name);
  const binding=scope.getBinding(name);
  if(!binding)throw Error('Unknown original binding '+name);
  if(binding.kind==='param')return;
  const p=binding.path;
  if(!p.isVariableDeclarator()&&!p.isFunctionDeclaration()&&!p.isClassDeclaration())throw Error('Unsupported binding '+name+' '+p.type);
  declarations.set(p.node.start,p.node);
  if(p.isVariableDeclarator())kinds.set(p.node.start,p.parentPath.node.kind);
  dependenciesOf(p);
  // Preserve separate TypeScript namespace initializers for selected bindings.
  // Never include enclosing app startup or a mutation buried in another function.
  for(const mutation of binding.constantViolations){
    if(mutation.scope!==scope)continue;
    const statement=mutation.findParent(p=>p.parentPath?.node===factory.node.body);
    if(statement?.isExpressionStatement()&&!declarations.has(statement.node.start)){
      declarations.set(statement.node.start,statement.node);
      dependenciesOf(statement);
    }
  }
}
Object.values(exportsMap).forEach(add);
const dependencies=new Set();
for(const reference of scope.getBinding(factory.node.params[2].name).referencePaths){
  const p=reference.parentPath;
  if(p.isCallExpression()&&p.node.callee===reference.node&&p.node.arguments[0]?.type==='StringLiteral'&&[...declarations.values()].some(node=>reference.node.start>=node.start&&reference.node.end<=node.end))dependencies.add(p.node.arguments[0].value);
}
const ordered=[...declarations.values()].sort((a,b)=>a.start-b.start);
const body=ordered.map(node=>node.type==='VariableDeclarator'?kinds.get(node.start)+' '+generate(node).code+';':generate(node).code).join('\n');
const params=factory.node.params.map(p=>p.name);
const exportCode=`${params[2]}.d(${params[1]},{${Object.entries(exportsMap).map(([name,value])=>`${name}:()=>${value}`).join(',')}});`;
const result=`(self.webpackChunkaurora_new_frontend=self.webpackChunkaurora_new_frontend||[]).push([[${JSON.stringify(derivedId)}],{${JSON.stringify(derivedId)}:function(${params.join(',')}){\n${body}\n${exportCode}\n}}]);\n`;
const provenance={sourceModule:moduleId,sourceFile:info.file,sourceFileSha256:crypto.createHash('sha256').update(source).digest('hex'),exports:exportsMap,selectedBindings:[...names],dependencies:[...dependencies],declarations:ordered.map(node=>({startUtf16:info.start+node.start-2,endUtf16:info.start+node.end-2})),derivedSha256:crypto.createHash('sha256').update(result).digest('hex'),limitation:'Original component rendering and dependencies only. No claim of complete application behavior.'};
const seen=new Set(),missing=new Set();
function visit(id){if(seen.has(id))return;seen.add(id);if(!index[id]){missing.add(id);return}index[id].imports.forEach(visit)}
dependencies.forEach(visit);
console.log(JSON.stringify({derivedId,exports:exportsMap,bindings:names.size,derivedBytes:Buffer.byteLength(result),missing:[...missing]},null,2));
return {result,provenance};
}
const modules=[
  derive('./packages/cad-pro/src/cad-pro-page.tsx',{RoofInsertOptions:'iQ',SiteToolbar:'ly',toolbarDefinitions:'lG',prepareToolbarItems:'lV',useToolbarStrings:'lh'},'local/captured-roof-ui'),
  derive('./packages/cad-core/src/use-cad/use-cad.tsx',{createUiState:'el',disposeUiState:'eu'},'local/captured-ui-state'),
  derive('./packages/cad-inspectors/src/index.ts',{RoofInspector:'l$',FaceInspector:'nz',DormerInspector:'nf',RoofPlaneInspector:'lV',PerimeterEdgeSection:'nU',selectionProps:'lP'},'local/captured-inspectors'),
  derive('./src/index.tsx',{ApolloClient:'rJ',InMemoryCache:'oB'},'local/captured-apollo'),
];
fs.writeFileSync(path.join(root,'local-roof-ui.js'),modules.map(x=>x.result).join('\n'),{mode:0o600});
fs.writeFileSync(path.join(root,'ui-provenance.json'),JSON.stringify(modules.map(x=>x.provenance),null,2),{mode:0o600});
