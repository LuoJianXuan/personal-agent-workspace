import fs from 'node:fs';
import Ajv from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
const schema=JSON.parse(fs.readFileSync('../../schemas/jsonschema/contracts.json','utf8'));
const ajv=new Ajv({strict:false});addFormats(ajv);ajv.addSchema(schema,'contracts');
for(const [file,name] of Object.entries({'model-write':'ModelWrite','skill-write':'SkillWrite','mcp-write':'McpWrite','discover-result':'DiscoverResult','start':'Start','snapshot':'Snapshot','event':'Event','events':'EventPage','approval':'Approval','tool-result':'ToolResult','file':'File','chart':'Chart'})){
 const value=JSON.parse(fs.readFileSync('../../schemas/examples/'+file+'.json','utf8'));const check=ajv.getSchema('contracts#/$defs/'+name);
 if(!check(value))throw Error(name+JSON.stringify(check.errors));value.unknown_field=true;if(check(value))throw Error('Unknown field accepted');
}
console.log('PASS: TS-consumer AJV accepts twelve shared fixtures and rejects unknown fields');
