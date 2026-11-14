(async()=>{
const app=PEP_SERVICES.qlik.getApp();
const {PAGE_CONFIGS}=await import('./config.js?v=1.4');
const diagnostics=window.__PEP_COLLECTOR_PROBE__={utc:new Date().toISOString(),filterCandidates:[],selectionTrace:[],mapping:null};
const trace=diagnostics.selectionTrace,boxes={};
const cargos=['Perito Criminal Federal 1a Cla','Perito Criminal Federal 2a Cla','Perito Criminal Federal 3a Cla','Perito Criminal Federal Classe'];
const expectedDims=['Grupo Situação do Vínculo','Nome do Cargo','Orgão','UF'];
// These are EXACT values/definitions observed in run-4 live public frontend metadata, not fuzzy aliases.
const nativeOrgaoField='Órgão (Servidores)', nativePfLabel='Departamento De Policia Federal';
const expectedPhysicalOrgao='Sigla Orgão Vinculado (Servidores)';
const equal=(a,b)=>JSON.stringify([...a].sort())===JSON.stringify([...b].sort());
async function box(parent){if(boxes[parent])return boxes[parent];const m=await app.getObjectProperties(parent);const l=await m.getLayout();if(l.qChildList.qItems.length!==1)throw new Error('Expected one public filter listbox for '+parent);const id=l.qChildList.qItems[0].qInfo.qId;const child=await app.getObjectProperties(id);return boxes[parent]={parent,id,model:child,definition:child.properties.qListObjectDef};}
async function values(b){const l=await b.model.getLayout();const count=l.qListObject.qDimensionInfo.qCardinal;if(count>10000)throw new Error('Bounded public filter cardinality exceeded');const d=await b.model.getListObjectData('/qListObjectDef',[{qTop:0,qLeft:0,qWidth:1,qHeight:Math.max(1,count)}]);return d.flatMap(p=>p.qMatrix.map(r=>r[0]));}
async function select(parent,label,targets){const b=await box(parent),v=await values(b);diagnostics.filterCandidates.push({label,parent,id:b.id,definition:b.definition,targets,values:v});const matches=targets.map(t=>{const found=v.filter(x=>x.qText===t);if(found.length!==1||!['O','A','S','L'].includes(found[0].qState))throw new Error('Unavailable/ambiguous '+label+': '+t);return found[0];});const result=await b.model.selectListObjectValues('/qListObjectDef',matches.map(x=>x.qElemNumber),false,false);const selected=(await values(b)).filter(x=>['S','L'].includes(x.qState)).map(x=>x.qText);if(!equal(selected,targets))throw new Error('Selection did not persist for '+label+': '+JSON.stringify(selected));trace.push({label,parent,id:b.id,fieldDefinition:b.definition.qDef.qFieldDefs,libraryId:b.definition.qLibraryId,requested:targets,selected,result});return b;}
// Public Capability createList, also used by the shipped frontend for default selections.
// Only reads its declared FVM field dictionary or its declared public organization-code field; no employee field/cube.
async function metadataList(field){return new Promise((resolve,reject)=>{let once=false;app.createList({qDef:{qFieldDefs:[field]},qInitialDataFetch:[{qTop:0,qLeft:0,qHeight:1000,qWidth:1}]},async reply=>{if(once)return;once=true;try{const l=reply.qListObject;const result={field,qInfo:reply.qInfo,dimension:l.qDimensionInfo,values:l.qDataPages.flatMap(p=>p.qMatrix.map(r=>r[0]))};if(l.qDimensionInfo.qCardinal>1000)throw new Error('Metadata cardinality bound exceeded');await app.destroySessionObject(reply.qInfo.qId);resolve(result);}catch(e){try{await app.destroySessionObject(reply.qInfo.qId);}catch{}reject(e);}});});}
const fvm=Object.fromEntries(PAGE_CONFIGS.fvm.filters.map(x=>[x.label,x.objectId]));
const servidores=Object.fromEntries(PAGE_CONFIGS.servidores.filters.map(x=>[x.label,x.objectId]));
await select(fvm['Seção'],'Seção',['Servidores']);
const pb=await box(fvm['Mês/Ano']);const pv=await values(pb);const eligible=pv.filter(x=>['O','A','S'].includes(x.qState)&&Number.isFinite(x.qNum));if(!eligible.length)throw new Error('No public reference months');const latest=eligible.reduce((a,b)=>a.qNum>b.qNum?a:b);
await select(fvm['Mês/Ano'],'Mês/Ano',[latest.qText]);
await select(servidores['Grupo Situação do Vinculo'],'Grupo Situação do Vinculo',['Ativo']);
const orgBox=await box(servidores['Orgão']);if(!equal(orgBox.definition.qDef.qFieldDefs,[nativeOrgaoField]))throw new Error('Native public Orgão field changed');
await select(servidores['Orgão'],'Orgão',[nativePfLabel]);
await select(fvm['Dimensão'],'Dimensão (mapping inspection)',['Orgão']);
const vis=await app.visualization.get(PAGE_CONFIGS.fvm.table);const properties=await vis.model.getProperties();
const fieldExpressions=properties.qHyperCubeDef.qDimensions.flatMap(d=>d.qDef?.qFieldDefs||[]);
const mappingExpression=fieldExpressions.find(s=>s.includes('FVM_CampoFisico'));if(!mappingExpression)throw new Error('Public FVM dictionary expression changed');
const physicalMapping=await metadataList('FVM_CampoFisico');const physicalFields=physicalMapping.values.filter(x=>['O','A','S','L'].includes(x.qState)).map(x=>x.qText);
diagnostics.mapping={nativeOrgaoField,nativePfLabel,mappingExpression,physicalMapping,physicalFields};
if(!equal(physicalFields,[expectedPhysicalOrgao]))throw new Error('Public FVM Orgão physical mapping changed: '+JSON.stringify(physicalFields));
const abbreviationMapping=await metadataList(physicalFields[0]);diagnostics.mapping.abbreviationMapping=abbreviationMapping;
const availableAbbreviations=abbreviationMapping.values.filter(x=>['O','A','S','L'].includes(x.qState)).map(x=>x.qText);
if(!equal(availableAbbreviations,['DPF']))throw new Error('Exact public PF name does not map exclusively to returned DPF: '+JSON.stringify(availableAbbreviations));
diagnostics.mapping.availableAbbreviations=availableAbbreviations;
const cb=await box(servidores['Cargo']);const cv=await values(cb);diagnostics.cargoCandidates=cv;
const candidates=cv.filter(x=>cargos.includes(x.qText)&&['O','A','S'].includes(x.qState)).map(x=>x.qText);if(!equal(candidates,cargos))throw new Error('Exact four PCF cargo contract changed: '+JSON.stringify(candidates));
await select(servidores['Cargo'],'Cargo',cargos);
await select(fvm['Dimensão'],'Dimensão',expectedDims);
await select(fvm['Métricas'],'Métricas',['Servidores']);
const finalSelections=[];for(const t of trace.filter(x=>x.label!=='Dimensão (mapping inspection)')){const b=await box(t.parent);const selected=(await values(b)).filter(x=>['S','L'].includes(x.qState)).map(x=>x.qText);if(!equal(selected,t.requested))throw new Error('Final selection drift: '+t.label);finalSelections.push({label:t.label,selected});}
const layout=await vis.model.getLayout(),cube=layout.qHyperCube;const dimensions=cube.qDimensionInfo.filter(x=>!x.qError).map(x=>x.qFallbackTitle);if(!equal(dimensions,['Ano','Mês',...expectedDims]))throw new Error('Unexpected returned public table dimensions: '+JSON.stringify(dimensions));
if(cube.qError?.qErrorCode||cube.qSize.qcx!==7||cube.qSize.qcy<1||cube.qSize.qcy>108||cube.qGrandTotalRow.length!==1||!Number.isSafeInteger(cube.qGrandTotalRow[0].qNum)||cube.qGrandTotalRow[0].qNum<0)throw new Error('Invalid aggregate table size/total');
const snapshot={utc:new Date().toISOString(),entry:location.href,appId:PEP_SERVICES.qlik.config.appId,table:PAGE_CONFIGS.fvm.table,title:layout.title,privileges:layout.qMeta.privileges,latest,availablePeriodCount:eligible.length,availablePeriods:pv,selectionTrace:trace,finalSelections,mapping:diagnostics.mapping,qSize:cube.qSize,dimensions,qGrandTotalRow:cube.qGrandTotalRow,measure:cube.qMeasureInfo.filter(x=>!x.qError).map(x=>({title:x.qFallbackTitle,minimum:x.qMin,maximum:x.qMax})),visibleText:document.querySelector('#page-fvm').innerText};
// Preparation only; controller next invokes the installed public download control with a user gesture.
return snapshot;
})()
