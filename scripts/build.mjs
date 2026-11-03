import { readdir, mkdir, copyFile, rm } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const out=join(root,'build/miniprogram');await rm(out,{recursive:true,force:true});
const result=spawnSync(process.execPath,[join(root,'node_modules/typescript/bin/tsc'),'-p',join(root,'tsconfig.json')],{stdio:'inherit'});if(result.status!==0)process.exit(result.status||1);
async function copy(dir,dst){await mkdir(dst,{recursive:true});for(const ent of await readdir(dir,{withFileTypes:true})){const from=join(dir,ent.name),to=join(dst,ent.name);if(ent.isDirectory())await copy(from,to);else if(!ent.name.endsWith('.ts'))await copyFile(from,to);}}
await copy(join(root,'miniprogram'),out);console.log('Built: '+out);
