// Offline asset inspection only. Does not connect to or operate a browser.
import { mkdir, writeFile } from 'node:fs/promises';
import * as THREE from 'three';
import { registerHooks } from 'node:module';
// The application bundler resolves extensionless TS imports; mirror that for this
// Node-only inspection script without changing the application's configuration.
registerHooks({ resolve(specifier, context, next) {
  return next(specifier === './push-up-rig' ? './push-up-rig.ts' : specifier, context);
} });
const { createStudio, INITIAL_YAW, INITIAL_PITCH } = await import('../components/scene/studio.ts');
import { depthAt, UPPER_ARM, FOREARM, BODY_LENGTH } from '../components/scene/push-up-rig.ts';
import assert from 'node:assert/strict';

const destination = new URL('../scene-checks/', import.meta.url);
await mkdir(destination, { recursive: true });
const studio = createStudio();
const report = { samples: 121, minMeshY: Infinity, armLengthError: 0, bodyAlignmentError: 0, topElbowAngle: 0, bottomElbowAngle: 0, bottomFlare: 0, triangleCount: 0, updateMilliseconds: 0, maxProjectedExtent: 0, geometryDrawGroups: 0 };
const started = performance.now();
for (let i = 0; i <= 120; i++) {
  const p = studio.update(i / 120);
  for (const side of p.sides) {
    report.armLengthError = Math.max(report.armLengthError, Math.abs(side.shoulder.distanceTo(side.elbow)-UPPER_ARM), Math.abs(side.elbow.distanceTo(side.wrist)-FOREARM));
    report.bodyAlignmentError = Math.max(report.bodyAlignmentError, Math.abs(p.shoulder.distanceTo(p.point(BODY_LENGTH))-BODY_LENGTH));
    assert.equal(side.wrist.x, .065);
    assert.equal(side.wrist.y, .131);
    assert(Math.abs(side.ankle.x - 1.25) < 1e-10);
    assert(Math.abs(side.ankle.y - .205) < 1e-10);
    const angle=THREE.MathUtils.radToDeg(side.shoulder.clone().sub(side.elbow).angleTo(side.wrist.clone().sub(side.elbow)));
    if (i===0) report.topElbowAngle=angle;
    if (i===120) {
      report.bottomElbowAngle=angle;
      report.bottomFlare=THREE.MathUtils.radToDeg(Math.atan2(Math.abs(side.elbow.z-side.shoulder.z),side.elbow.x-side.shoulder.x));
    }
  }
  for (const mesh of studio.meshes.filter(m=>/shirt|waist|neck|head|arm|leg-|palm-|thumb|trainer/.test(m.name) && !/tripod|zone/.test(m.name))) {
    const pos=mesh.geometry.attributes.position;
    for(let j=0;j<pos.count;j++) report.minMeshY=Math.min(report.minMeshY,pos.getY(j));
  }
}
report.updateMilliseconds=(performance.now()-started)/121;
report.triangleCount=studio.meshes.reduce((n,m)=>n+(m.geometry.index?.count ?? m.geometry.attributes.position.count)/3,0);
assert(report.armLengthError < 1e-8);
assert(report.bodyAlignmentError < 1e-8);
assert(report.minMeshY >= .06, 'Body intersects the mat');
assert(report.topElbowAngle > 155 && report.topElbowAngle < 179);
assert(report.bottomElbowAngle >= 80 && report.bottomElbowAngle <= 100);
assert(report.bottomFlare >= 35 && report.bottomFlare <= 50);
assert.equal(depthAt(0),depthAt(4.6));
report.geometryDrawGroups=studio.meshes.reduce((n,m)=>n+(Array.isArray(m.material)?m.geometry.groups.length:1),0);
for(const depth of [0,.5,1]) for(const aspect of [740/650,520/594,358/424,288/424]) {
  studio.update(depth);
  for(const yaw of [INITIAL_YAW-.5,INITIAL_YAW,INITIAL_YAW+.5]) for(const pitch of [.35,INITIAL_PITCH,.72]) {
    studio.compose(aspect,yaw,pitch);
    for(const mesh of studio.meshes.filter(m=>m.name!=='studio-floor')) {
      const p=mesh.geometry.attributes.position;
      for(let i=0;i<p.count;i++) {
        const point=new THREE.Vector3().fromBufferAttribute(p,i).applyMatrix4(mesh.matrixWorld).project(studio.camera);
        report.maxProjectedExtent=Math.max(report.maxProjectedExtent,Math.abs(point.x),Math.abs(point.y));
      }
    }
  }
}
assert(report.maxProjectedExtent < .90, 'Object clipped during allowed camera rotation');
await writeFile(new URL('constraints.json',destination),JSON.stringify(report,null,2));
console.log(report);

for (const [name, depth, width, height] of [
  ['desktop-top',0,740,650],['desktop-middle',.5,740,650],['desktop-bottom',1,740,650],
  ['mobile-top',0,358,424],['mobile-bottom',1,358,424],
]) {
  studio.update(depth); studio.compose(width/height);
  const data={name,width,height,camera:{position:studio.camera.position.toArray(),quaternion:studio.camera.quaternion.toArray(),fov:studio.camera.fov},meshes:[]};
  for(const mesh of studio.meshes) {
    const g=mesh.geometry, pos=g.attributes.position, vertices=[];
    for(let i=0;i<pos.count;i++) vertices.push(new THREE.Vector3().fromBufferAttribute(pos,i).applyMatrix4(mesh.matrixWorld).toArray());
    const indices=g.index ? Array.from(g.index.array):Array.from({length:pos.count},(_,i)=>i);
    const materials=(Array.isArray(mesh.material)?mesh.material:[mesh.material]).map(m=>({color:m.color.toArray(),roughness:m.roughness,metalness:m.metalness}));
    data.meshes.push({name:mesh.name,vertices,indices,groups:g.groups,materials});
  }
  await writeFile(new URL(`${name}.json`,destination),JSON.stringify(data));
}
if (process.argv.includes('--animation')) {
  const frames=[];
  for(let i=0;i<138;i++) {
    studio.update(depthAt(i/30));
    const frame={};
    for(const mesh of studio.meshes.filter(m=>/fitted-shirt|waist|neck|sculpted-head|continuous/.test(m.name))) {
      frame[mesh.name]=Array.from(mesh.geometry.attributes.position.array, n=>Math.round(n*1e6)/1e6);
    }
    frames.push(frame);
  }
  await writeFile(new URL('animation.json',destination),JSON.stringify(frames));
}
studio.dispose();
