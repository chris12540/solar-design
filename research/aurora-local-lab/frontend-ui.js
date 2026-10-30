// Original captured React components mounted through their existing providers.
const moduleName={
  react:'./node_modules/react/index.js',
  dom:'./node_modules/react-dom/client.js',
  ds:'./node_modules/@aurorasolar/ds/dist/index.esm.js',
  context:'./packages/cad-core/src/use-cad/cad-context.tsx',
};
const script = src => new Promise((resolve,reject)=>{
  const node=document.createElement('script');node.src=src;
  node.onload=resolve;node.onerror=()=>reject(new Error('Missing local frontend asset: '+src));
  document.head.append(node);
});

export async function prepareOriginalUi() {
  const evidence=window.lab.originalUi={status:'loading',errors:[]};
  const manifest=await fetch('/frontend-capture.json').then(response=>{if(!response.ok)throw Error('Frontend capture missing');return response.json()});
  await script('/frontend-assets/frontend-runtime.js');
  // Fixed registration order for duplicated modules emitted in shared chunks.
  for(const file of manifest.files)await script('/frontend-assets/'+file);
  await script('/frontend-assets/local-roof-ui.js');
  const require=window.__auroraFrontendRequire;
  return {stateFramework:require('./packages/state/src/framework.ts').cq,reactiveInstance:require('./node_modules/@aurorasolar/reactive/chunk-FGEKKLM2.mjs').xZ(),mount:engine=>mountOriginalRoofUi(engine,require)};
}

function mountOriginalRoofUi(engine,require) {
  const evidence=window.lab.originalUi;
  const React=require(moduleName.react),ReactDOM=require(moduleName.dom),DS=require(moduleName.ds),CadContext=require(moduleName.context);
  const {RoofInsertOptions,SiteToolbar,toolbarDefinitions,prepareToolbarItems,useToolbarStrings}=require('local/captured-roof-ui');
  const StableSiteToolbar=React.memo(SiteToolbar),StableRoofInsertOptions=React.memo(RoofInsertOptions);
  const noop=()=>{};
  const {createUiState,disposeUiState}=require('local/captured-ui-state');
  const inspectorViews=require('local/captured-inspectors');
  const {ApolloClient,InMemoryCache}=require('local/captured-apollo');
  const ApolloContext=require('./node_modules/@apollo/client/react/context/ApolloContext.js').l();
  const ApolloLink=require('./node_modules/@apollo/client/link/core/ApolloLink.js').C;
  const Observable=require('./node_modules/zen-observable-ts/module.js').c;
  const gql=require('./node_modules/graphql-tag/lib/index.js').J1;
  const schema=require('./packages/graphql-client-schema/src/generated-schema.ts');
  const cache=new InMemoryCache();
  cache.writeQuery({query:gql`query LocalUnits { apiInfo { tenant { id distanceUnit: units temperatureUnit } } }`,data:{apiInfo:{__typename:'ApiInfo',tenant:{__typename:'Tenant',id:'local-lab',distanceUnit:schema.yV.Metric,temperatureUnit:schema.pb.C}}}});
  evidence.localMetadataRequests=[];
  const client=new ApolloClient({cache,connectToDevTools:false,link:new ApolloLink(operation=>new Observable(observer=>{
    evidence.localMetadataRequests.push(operation.operationName);
    observer.error(new Error('No local adapter for query '+operation.operationName));
  }))});
  const uiState=createUiState(engine.state);
  const cadActions=require('./packages/common/packages/data-store/src/redux/CAD/actions.ts');
  const inspectorRoot=document.createElement('section');inspectorRoot.id='original-inspector-root';
  inspectorRoot.style.cssText='position:relative;width:100%;height:100%;pointer-events:auto';
  const aside=document.querySelector('aside');
  aside.prepend(inspectorRoot);
  const portals=require('./node_modules/react-dom/index.js');
  const root=document.createElement('section');root.id='original-ui-root';
  root.style.cssText='position:absolute;inset:0;z-index:10;pointer-events:none';
  document.querySelector('#viewport').append(root);
  class Boundary extends React.Component {
    state={error:null};
    static getDerivedStateFromError(error){return {error};}
    componentDidCatch(error){evidence.status='error';evidence.errors.push(error.stack||error.message);}
    render(){return this.state.error?React.createElement('span',null,'Roof controls could not load'):this.props.children;}
  }
  // Undo can restore neighbor positions without refreshing the native angle cache.
  function measuredCornerAngle(node) {
    if(!node||node.edges.length!==2)return undefined;
    const adjacent=node.edges.map(edge=>edge.nodes.find(n=>n!==node));
    if(adjacent.some(n=>!n))return undefined;
    const [a,b]=adjacent.map(n=>({x:n.x-node.x,y:n.y-node.y}));
    if(Math.hypot(a.x,a.y)<1e-9||Math.hypot(b.x,b.y)<1e-9)return undefined;
    return Math.atan2(Math.abs(a.x*b.y-a.y*b.x),a.x*b.x+a.y*b.y)*180/Math.PI;
  }
  const hasRoofDetails=roof=>!!(roof?.dormers?.length||roof?.kinks?.length);
  function CornerInspector({id}) {
    const node=engine.dataStore.find(id),angle=measuredCornerAngle(node);
    const [value,setValue]=React.useState(''),[edited,setEdited]=React.useState(false),[opposite,setOpposite]=React.useState(false),[error,setError]=React.useState('');
    React.useEffect(()=>{setValue(Number.isFinite(angle)?String(Number(angle.toFixed(2))):'');setEdited(false);setError('');},[id,angle]);
    if(!node)return null;
    const roof=node.roof,canRemove=!!roof?.isLoop&&roof.perimeterNodes.length>3&&node.edges.length===2&&!hasRoofDetails(roof);
    const remove=()=>{
      const current=engine.dataStore.find(id),parent=current?.roof;
      if(!parent?.isLoop||parent.perimeterNodes.length<=3||current.edges.length!==2||hasRoofDetails(parent))return;
      const neighbor=current.edges[0].otherNode(current);
      parent.closePerimeter(current);
      engine.dataStore.commit();
      if(neighbor&&!neighbor.isDestroyed)engine.triggerAction('selectEntitiesByIds',{entityIds:[neighbor.id]});
      document.querySelector('#viewport').focus();
    };
    const apply=event=>{
      event.preventDefault();
      if(!edited)return;
      const target=Number(value);
      if(!Number.isFinite(target)||target<=0||target>180){setError('Enter an angle greater than 0° and at most 180°.');return;}
      const current=engine.dataStore.find(id);
      if(!current?.roof?.isLoop||current.edges.length!==2){setError('Finish the roof outline before editing this corner.');return;}
      if(Math.abs(measuredCornerAngle(current)-target)<1e-9)return;
      setError('');
      engine.triggerAction('changePerimeterNodeAngle',{newAngle:target,anchorSide:opposite?'anchorRight':'anchorLeft'});
      setEdited(false);
      document.querySelector('#viewport').focus();
    };
    return React.createElement('section',{className:'local-corner-inspector'},
      React.createElement('h2',null,'Roof corner'),
      React.createElement('p',null,'Set the angle between adjoining edges in plan view. This corner stays fixed; one adjacent corner moves.'),
      React.createElement('form',{onSubmit:apply,onKeyDown:event=>event.stopPropagation(),onKeyUp:event=>event.stopPropagation()},
        React.createElement('label',null,'Plan angle (°)',React.createElement('input',{type:'number',min:0.01,max:180,step:'any',required:true,value,onChange:event=>{setValue(event.target.value);setEdited(true)},'data-testid':'corner-angle','aria-label':'Roof corner angle'})),
        React.createElement('label',{className:'local-corner-option'},React.createElement('input',{type:'checkbox',checked:opposite,onChange:event=>setOpposite(event.target.checked),'aria-label':'Move opposite adjacent corner'}),'Move opposite adjacent corner'),
        error&&React.createElement('p',{role:'alert'},error),
        React.createElement('button',{type:'submit'},'Apply angle')),
      React.createElement('button',{type:'button',className:'local-remove-corner',disabled:!canRemove,onClick:remove},'Remove corner'),
      !canRemove&&React.createElement('p',{className:'local-corner-limit'},hasRoofDetails(roof)?'Finish the outline before adding dormers or folds. Remove those details before changing corner count.':roof?.isLoop?'A roof needs at least three corners.':'Finish the roof outline before removing corners.'));
  }
  // These ring primitives belong to the pinned native engine; it rebuilds faces.
  function EdgeCornerControl({id}) {
    const edge=engine.dataStore.find(id),roof=edge?.roof,nodes=edge?.nodes;
    const canAdd=roof?.isLoop&&!hasRoofDetails(roof)&&nodes?.length===2&&Math.hypot(nodes[1].x-nodes[0].x,nodes[1].y-nodes[0].y)>1e-6;
    const add=()=>{
      const current=engine.dataStore.find(id),parent=current?.roof,ends=current?.nodes;
      if(!parent?.isLoop||hasRoofDetails(parent)||ends?.length!==2)return;
      const [a,b]=ends;
      if(Math.hypot(b.x-a.x,b.y-a.y)<=1e-6)return;
      const attributes=current.serialize();
      const corner=parent._makeNewNode(null,(a.x+b.x)/2,(a.y+b.y)/2);
      current.destroy();
      parent._makeNewEdge(attributes,a,corner);
      parent._makeNewEdge(attributes,corner,b);
      engine.dataStore.commit();
      engine.triggerAction('selectEntitiesByIds',{entityIds:[corner.id]});
      document.querySelector('#viewport').focus();
    };
    return React.createElement('section',{className:'local-edge-corner-control'},
      React.createElement('button',{type:'button',disabled:!canAdd,onClick:add},'Add corner at midpoint'),
      React.createElement('p',null,hasRoofDetails(roof)?'Finish the outline before adding dormers or folds. Remove those details before changing corner count.':canAdd?'Then drag the new white corner to reshape the outline.':'Finish the roof outline before adding corners.'));
  }
  function PerimeterEdgeFields({selection}) {
    const root=React.useRef(null);
    // Retained controls have icon-only endpoint choices and an unlabeled field.
    // Add host accessibility metadata without replacing their native edit handlers.
    React.useLayoutEffect(()=>{
      const field=root.current?.querySelector('[data-testid="perimeterEdges-length"]');
      if(!field)return;
      field.setAttribute('aria-label','Roof edge length in meters');
      field.setAttribute('aria-describedby','local-edge-length-help');
      for(const [key,label] of [['anchorLeft','Keep second corner fixed'],['anchorRight','Keep first corner fixed']]){
        const button=root.current.querySelector(`button[data-key="${key}"]`);
        if(button){button.setAttribute('aria-label',label);button.setAttribute('title',label);}
      }
    });
    return React.createElement('div',{ref:root},React.createElement(inspectorViews.PerimeterEdgeSection,{perimeterEdges:selection}));
  }
  // Starter presets only set native edge pitches. Native CAD constructs the roof.
  function starterEdges(roof) {
    if(!roof||roof.type!=='roof'||!roof.isLoop||!roof.isValid||!roof.isConstructed||hasRoofDetails(roof))return null;
    const edges=roof.perimeterEdges,nodes=roof.perimeterNodes;
    if(edges.length!==4||nodes.length!==4)return null;
    if(edges.some(e=>!Number.isFinite(e.height)||Math.abs(e.height-edges[0].height)>1e-7))return null;
    for(const node of nodes){
      if(node.edges.length!==2)return null;
      const [a,b]=node.edges.map(e=>e.otherNode(node)),u=[a.x-node.x,a.y-node.y],v=[b.x-node.x,b.y-node.y];
      const scale=Math.hypot(...u)*Math.hypot(...v);
      if(!Number.isFinite(scale)||scale<1e-8||Math.abs(u[0]*v[0]+u[1]*v[1])/scale>1e-6)return null;
    }
    const first=edges[0],next=first.nodes[1].edges.find(e=>e!==first),opposite=edges.find(e=>e.nodes.every(n=>!first.nodes.includes(n))),last=edges.find(e=>e!==first&&e!==next&&e!==opposite);
    return next&&opposite&&last?[first,next,opposite,last]:null;
  }
  function rectangleFrame(roof) {
    const edges=starterEdges(roof);if(!edges)return null;
    const [a,b]=edges[0].nodes,d=edges[3].otherNode(a),width=Math.hypot(b.x-a.x,b.y-a.y),depth=Math.hypot(d.x-a.x,d.y-a.y);
    const center=roof.perimeterNodes.reduce((p,n)=>({x:p.x+n.x/4,y:p.y+n.y/4}),{x:0,y:0});
    return {roof,width,depth,center,u:{x:(b.x-a.x)/width,y:(b.y-a.y)/width},v:{x:(d.x-a.x)/depth,y:(d.y-a.y)/depth}};
  }
  function RectangleSize({id}) {
    const frame=rectangleFrame(engine.dataStore.find(id)),actualWidth=frame?.width,actualDepth=frame?.depth;
    const [width,setWidth]=React.useState(''),[depth,setDepth]=React.useState(''),[widthEdited,setWidthEdited]=React.useState(false),[depthEdited,setDepthEdited]=React.useState(false),[error,setError]=React.useState('');
    React.useEffect(()=>{
      setWidth(Number.isFinite(actualWidth)?String(Number(actualWidth.toFixed(3))):'');setDepth(Number.isFinite(actualDepth)?String(Number(actualDepth.toFixed(3))):'');
      setWidthEdited(false);setDepthEdited(false);setError('');
    },[id,actualWidth,actualDepth]);
    const apply=event=>{
      event.preventDefault();const current=rectangleFrame(engine.dataStore.find(id));
      if(!current){setError('Resize a rectangle with equal edge heights, before adding details.');return;}
      if(!widthEdited&&!depthEdited)return;
      const w=widthEdited?Number(width):current.width,h=depthEdited?Number(depth):current.depth;
      if(![w,h].every(n=>Number.isFinite(n)&&n>=0.1&&n<=1000)){setError('Enter dimensions from 0.1 to 1000 meters.');return;}
      setError('');if(Math.abs(w-current.width)<1e-9&&Math.abs(h-current.depth)<1e-9)return;
      const {center,u,v}=current;
      const positions=current.roof.perimeterNodes.map(node=>{
        const x=node.x-center.x,y=node.y-center.y,su=Math.sign(x*u.x+y*u.y),sv=Math.sign(x*v.x+y*v.y);
        return {node,x:center.x+su*w*u.x/2+sv*h*v.x/2,y:center.y+su*w*u.y/2+sv*h*v.y/2};
      });
      for(const p of positions){p.node.x=p.x;p.node.y=p.y;}
      engine.dataStore.commit();document.querySelector('#viewport').focus();
    };
    return React.createElement('section',{className:'local-rectangle-size'},
      React.createElement('h4',null,'Footprint size'),
      React.createElement('p',null,'Resize around the center. Width follows the first outline edge; depth runs across it. Pitch and edge heights stay fixed.'),
      React.createElement('form',{onSubmit:apply,onKeyDown:event=>event.stopPropagation(),onKeyUp:event=>event.stopPropagation()},
        React.createElement('label',null,'Width (m)',React.createElement('input',{'aria-label':'Rectangle footprint width',type:'number',required:true,min:0.1,max:1000,step:'any',disabled:!frame,value:width,onChange:event=>{setWidth(event.target.value);setWidthEdited(true);}})),
        React.createElement('label',null,'Depth (m)',React.createElement('input',{'aria-label':'Rectangle footprint depth',type:'number',required:true,min:0.1,max:1000,step:'any',disabled:!frame,value:depth,onChange:event=>{setDepth(event.target.value);setDepthEdited(true);}})),
        React.createElement('button',{type:'submit',disabled:!frame},'Resize rectangle')),
      error&&React.createElement('p',{role:'alert'},error));
  }
  function RoofStarter({id}) {
    const roof=engine.dataStore.find(id),eligible=!!starterEdges(roof);
    const [kind,setKind]=React.useState('gable'),[pitch,setPitch]=React.useState('30'),[direction,setDirection]=React.useState(0),[error,setError]=React.useState('');
    React.useEffect(()=>{setKind('gable');setPitch('30');setDirection(0);setError('');},[id]);
    const apply=(turn=0)=>{
      const edges=starterEdges(engine.dataStore.find(id)),angle=Number(pitch);
      if(!edges){setError('Use a rectangle with equal edge heights, before adding dormers or folds.');return;}
      if(!Number.isFinite(angle)||angle<=0||angle>80){setError('Enter a pitch greater than 0° and at most 80°.');return;}
      const count=kind==='gable'?2:4,index=(direction+turn)%count;
      const values=edges.map((_,i)=>kind==='hip'||i===index||(kind==='gable'&&i===(index+2)%4)?angle:90);
      setDirection(index);setError('');
      if(values.some((value,i)=>Math.abs(edges[i].pitch-value)>1e-9)){
        edges.forEach((edge,i)=>{edge.pitch=values[i];});
        engine.dataStore.commit();
      }
      document.querySelector('#viewport').focus();
    };
    return React.createElement('section',{className:'local-roof-starter'},
      React.createElement('h3',null,'Roof starter'),
      React.createElement('p',null,eligible?'Apply a shape to this rectangle. Footprint and edge heights stay fixed.':'Use a rectangle with equal edge heights, before adding dormers or folds.'),
      React.createElement('form',{onSubmit:event=>{event.preventDefault();apply();},onKeyDown:event=>event.stopPropagation(),onKeyUp:event=>event.stopPropagation()},
        React.createElement('label',null,'Shape',React.createElement('select',{'aria-label':'Roof starter shape',value:kind,onChange:event=>{setKind(event.target.value);setDirection(0);}},...['hip','gable','shed'].map(value=>React.createElement('option',{key:value,value},value[0].toUpperCase()+value.slice(1))))),
        React.createElement('label',null,'Pitch (°)',React.createElement('input',{'aria-label':'Roof starter pitch',type:'number',required:true,min:0.01,max:80,step:'any',value:pitch,onChange:event=>setPitch(event.target.value)})),
        React.createElement('button',{type:'submit',disabled:!eligible},'Apply roof starter'),
        React.createElement('button',{type:'button',disabled:!eligible||kind==='hip',onClick:()=>apply(1)},'Turn starter 90°')),
      error&&React.createElement('p',{role:'alert'},error),
      React.createElement(RectangleSize,{id}));
  }
  function Inspector(){
    const corners=engine.bridge.serializeSelection().filter(selected=>selected.type==='node.perimeter');
    const supported=['roofs','perimeterEdges','dormers','kinks','roofPlanes'];
    const active=uiState.data.activeTabData.activeTab;
    const type=corners.length?null:supported.includes(active)&&uiState.data.selectionData[active].count>0?active:uiState.data.inspectorData.selectedTypes.find(type=>supported.includes(type));
    React.useEffect(()=>{if(type&&type!==active)uiState.actions.activeTabActions.setActiveTab(type);},[type,active]);
    if(corners.length===1)return React.createElement(CornerInspector,{id:corners[0].data.id});
    if(corners.length>1)return React.createElement('p',{className:'local-authoring-hint'},'Select one roof corner to edit its angle.');
    if(!type)return React.createElement(DS.Text,{p:4,children:'Select a roof, face, dormer, or fold.'});
    const selection=inspectorViews.selectionProps(uiState,type)[type];
    const action=(name,props)=>()=>engine.triggerAction(name,props);
    if(type==='roofs')return React.createElement(React.Fragment,null,
      engine.bridge.serializeSelection().filter(item=>item.type==='roof').length===1&&React.createElement(RoofStarter,{id:engine.bridge.serializeSelection().find(item=>item.type==='roof').data.id}),
      React.createElement(inspectorViews.RoofInspector,{
      roofs:selection,roofType:selection.inFlatMode?'flat':'pitched',isLidarAvailable:false,lidarTooltip:'No height-data adapter loaded',
      onEditRoofClicked:action('enterRoofIsolationMode'),onExplodeClicked:action('explodeRoof'),onFitToLidarClicked:()=>{},onMoveClicked:action('moveRoof'),
      onRoofTypeChanged:type=>engine.triggerAction(type==='flat'?'flattenRoof':'pitchUpRoof'),onRoofUsageTypeToggled:value=>selection.setBuildingUsageType(value?'primary':'accessory'),
    }));
    if(type==='perimeterEdges')return React.createElement(React.Fragment,null,
      React.createElement('p',{id:'local-edge-length-help',className:'local-authoring-hint'},'Length is in meters. The circle marks the fixed end; the arrow marks the moving end. Choose an end, enter Length, then click outside the field to apply. Adjoining edges will change. Select a roof corner to set its angle.'),
      engine.bridge.serializeSelection().filter(item=>item.type==='edge.perimeter').length===1&&React.createElement(EdgeCornerControl,{id:engine.bridge.serializeSelection().find(item=>item.type==='edge.perimeter').data.id}),
      React.createElement(inspectorViews.FaceInspector,{cadModelType:'edge.perimeter',faces:selection,perimeterEdgeSection:React.createElement(PerimeterEdgeFields,{selection})}));
    if(type==='kinks')return React.createElement(inspectorViews.FaceInspector,{cadModelType:'kink',faces:selection});
    if(type==='dormers')return React.createElement(inspectorViews.DormerInspector,{dormers:selection,convertToRoof:action('convertToRoof')});
    return React.createElement(React.Fragment,null,
      React.createElement('p',{className:'local-authoring-hint'},'Drag this face’s outline to resize it. Change its height or pitch below.'),
      React.createElement(inspectorViews.RoofPlaneInspector,{roofPlanes:selection,isLidarAvailable:false,lidarTooltip:'No height-data adapter loaded',onFitToLidarClicked:()=>{},onMoveClicked:action('moveRoof'),onRoofUsageTypeToggled:value=>selection.setBuildingUsageType(value?'primary':'accessory')}));
  }
  function Bridge(){
    const actions=CadContext.jY();
    const [,refresh]=React.useReducer(n=>n+1,0);
    const [collapsed,setCollapsed]=React.useState(false);
    const toggleCollapsed=React.useCallback(()=>setCollapsed(v=>!v),[]);
    const {t}=useToolbarStrings();
    const mode=engine.subsystems.modeManager.actualStateMode;
    React.useLayoutEffect(()=>{
      actions.setCadContext({engine,state:uiState,designId:'local-synthetic',engineSaveFn:()=>engine.bridge.save(),domNode:document.querySelector('#viewport')});
      const timer=setInterval(refresh,150);
      evidence.status='ready';
      for(const element of aside.children)if(element!==inspectorRoot)element.style.display='none';
      aside.style.padding='0';
      for(const action of ['drawPitchedRoof','drawFlatRoof','drawRoofPlane'])document.querySelector(`[data-action="${action}"]`).style.display='none';
      return()=>{clearInterval(timer);actions.clearCadContext();disposeUiState(uiState);client.stop();};
    },[actions]);
    const publicMode=engine.subsystems.modeManager.getPublicModeName();
    const canUndo=engine.dataStore.versioner.canUndo,canRedo=engine.dataStore.versioner.canRedo;
    const roofCount=engine.dataStore.findAllHeirs('roof').length;
    const groups=React.useMemo(()=>{
    const context={
      project:{projectType:'residential'},
      cadState:{mode:publicMode,canUndo,canRedo,isAutoRoofRunning:false},
      toolbarCadState:{roofCount,enabledPanelCount:0,existingPanelCount:0,selectedSolarPanelCount:0,panelTypes:[]},
      featureFlags:{variation:()=>false},permissions:{getPermission:()=>false},
      lidar:{isResolved:true,isAvailable:false},disabled:false,t,
      triggerCadAction:(action,props)=>engine.triggerAction(action,props),track:()=>{},
      openDrawer:()=>{},openModal:()=>{},openPerformancePanel:()=>{},notify:{push:()=>{}},
    };
    return [{key:'local-site',items:prepareToolbarItems(t,toolbarDefinitions('default-site'),context)}];
    },[publicMode,canUndo,canRedo,roofCount,t]);
    return React.createElement(React.Fragment,null,
      React.createElement('div',{style:{position:'absolute',top:16,left:16,pointerEvents:'auto'},'data-testid':'original-site-toolbar'},React.createElement(StableSiteToolbar,{groups,isCollapsed:collapsed,hideSystemItems:true,onToggleCollapsed:toggleCollapsed,onModeChanged:noop,onToggleMode:noop,uberMode:cadActions.GF.Site})),
      mode.endsWith(':roof')&&React.createElement('div',{'data-testid':'original-roof-options',style:{position:'absolute',bottom:24,left:16,pointerEvents:'auto',padding:'10px 14px',background:'white',borderRadius:6,boxShadow:'0 4px 20px #0002'}},React.createElement(StableRoofInsertOptions)),
      portals.createPortal(React.createElement(Inspector),inspectorRoot));
  }
  ReactDOM.createRoot(root).render(React.createElement(Boundary,null,React.createElement(ApolloContext.Provider,{value:{client}},React.createElement(DS.StyleProvider,{theme:DS.BorealisTheme,colorMode:'light'},React.createElement(CadContext.P8,null,React.createElement(Bridge))))));
}
