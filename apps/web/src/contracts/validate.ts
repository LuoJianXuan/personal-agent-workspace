import Ajv from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import schema from './schema.json';
const ajv = new Ajv({strict:false});
addFormats(ajv); ajv.addSchema(schema, 'contracts');
export function validate<T>(name:string, value:unknown):T {
 const check=ajv.getSchema(`contracts#/$defs/${name}`);
 if(!check || !check(value)) throw new Error('服务返回的数据不符合共享契约');
 return value as T;
}
