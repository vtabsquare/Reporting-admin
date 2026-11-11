const fs=require('fs');
const assert=require('assert');

const component=fs.readFileSync('src/WorkspaceDetailWithPermissions.tsx','utf8');
const styles=fs.readFileSync('src/WorkspaceDetailPermissions.css','utf8');
const app=fs.readFileSync('src/App.tsx','utf8');

const expected=[
  ['can_file','File menu'],
  ['can_home','Home ribbon'],
  ['can_view','View ribbon'],
  ['can_share','Share'],
  ['can_pdf','PDF'],
  ['can_ppt','PowerPoint'],
  ['can_refresh','Refresh'],
  ['can_subscribe','Subscribe'],
  ['can_alert','Alerts'],
  ['can_download','Download project'],
];

for(const[key,label]of expected){
  assert(component.includes(`{key:'${key}',label:'${label}'}`),`${label} must map to ${key}`);
}
assert(component.includes('data-permission-key={permissionKey}'),'every switch must carry its explicit permission key');
assert(component.includes('permissionKey={option.key}'),'rendered controls must bind their own option key');
assert(styles.includes('justify-content:flex-start'),'switches and labels must remain visually adjacent');
assert(!app.includes("http://127.0.0.1:8835/api"),'Admin UI must not bypass the configured API proxy');

console.log('Admin permission switch mapping contract passed.');
