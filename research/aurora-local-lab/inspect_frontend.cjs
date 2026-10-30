// Inert syntax inventory. Does not execute vendor code or contact a server.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const parser = require('/Users/chris/code/solar-designer/frontend/node_modules/@babel/parser');
const traverse = require('/Users/chris/code/solar-designer/frontend/node_modules/@babel/traverse').default;
const root = path.join(__dirname, 'runtime', 'frontend');
const index = {};
const variants = {};
const walk = (node, visit) => {
  if (!node || typeof node !== 'object') return;
  visit(node);
  for (const [key,value] of Object.entries(node)) {
    if (key === 'loc') continue;
    if (Array.isArray(value)) value.forEach(child => walk(child,visit));
    else if (value && typeof value === 'object') walk(value,visit);
  }
};
for (const file of fs.readdirSync(root).filter(name => name.endsWith('.prod.js')).sort()) {
  const source = fs.readFileSync(path.join(root,file),'utf8');
  const ast = parser.parse(source, { sourceType:'script' });
  traverse(ast, { CallExpression(callPath) {
    const node=callPath.node;
    if (node.type !== 'CallExpression' || node.callee?.property?.name !== 'push') return;
    const modules = node.arguments[0]?.elements?.[1];
    if (modules?.type !== 'ObjectExpression') return;
    const itemPaths=callPath.get('arguments.0.elements.1.properties');
    for (const itemPath of itemPaths) {
      const item=itemPath.node;
      const id = item.key?.value ?? item.key?.name;
      const factory = item.type === 'ObjectMethod' ? item : item.value;
      if (!id || !factory || !['ObjectMethod','ArrowFunctionExpression','FunctionExpression'].includes(factory.type)) continue;
      const requireName = factory.params?.[2]?.name;
      const imports = new Set(), chunks = new Set();
      const factoryPath=item.type==='ObjectMethod'?itemPath:itemPath.get('value');
      const binding=requireName?factoryPath.scope.getBinding(requireName):undefined;
      for(const reference of binding?.referencePaths||[]){
        const parent=reference.parentPath;
        if(parent.isCallExpression()&&parent.node.callee===reference.node&&parent.node.arguments[0]?.type==='StringLiteral')imports.add(parent.node.arguments[0].value);
        if(parent.isMemberExpression()&&parent.node.property?.name==='e'&&parent.parentPath.isCallExpression()&&parent.parentPath.node.arguments[0]?.type==='StringLiteral')chunks.add(parent.parentPath.node.arguments[0].value);
      }
      const digest = crypto.createHash('sha256').update(source.slice(factory.start,factory.end)).digest('hex');
      if(index[id] && index[id].sha256 !== digest){
        if(!variants[id])variants[id]=[index[id]];
        variants[id].push({file,start:factory.start,end:factory.end,sha256:digest,imports:[...imports],chunks:[...chunks]});
      }
      index[id] = { file, start:factory.start, end:factory.end, sha256:digest, imports:[...imports], chunks:[...chunks] };
    }
  }});
}
fs.writeFileSync(path.join(root,'module-index.json'),JSON.stringify(index,null,2),{mode:0o600});
fs.writeFileSync(path.join(root,'module-variants.json'),JSON.stringify(variants,null,2),{mode:0o600});
const pattern = new RegExp(process.argv[2] || 'roof|toolbar|cad-pro-routes','i');
const matches = Object.keys(index).filter(id=>pattern.test(id));
console.log(JSON.stringify({ modules:Object.keys(index).length, variantModules:Object.keys(variants).length, matching:matches.length, matches:matches.slice(0,140) },null,2));
