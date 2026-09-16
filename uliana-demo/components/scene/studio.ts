import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';
import { poseAt, MAT_TOP } from './push-up-rig';

const v = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const UP = v(0, 1, 0);
export const INITIAL_YAW = 1.16;
export const INITIAL_PITCH = 0.51;
const material = (color: string, roughness = 0.8) => new THREE.MeshStandardMaterial({ color, roughness });

// Ring lofts form continuous anatomical surfaces. There are no exposed joint balls
// or separately scaled cylinders. The surfaces follow the solved skeleton.
function surface(rings = 40, segments = 16) {
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array((rings + 1) * (segments + 1) * 3);
  const indices: number[] = [];
  for (let i = 0; i < rings; i++) for (let j = 0; j < segments; j++) {
    const a = i * (segments + 1) + j, b = a + segments + 1;
    indices.push(a, b, a + 1, b, b + 1, a + 1);
  }
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  return { geometry, rings, segments };
}
type Surface = ReturnType<typeof surface>;
function assignMaterials(s: Surface, select: (ring: number, segment: number) => number) {
  const source = Array.from(s.geometry.index!.array);
  const groups: number[][] = [[], []];
  for (let i=0;i<s.rings;i++) for(let j=0;j<s.segments;j++) {
    const offset=(i*s.segments+j)*6;
    groups[select(i,j)].push(...source.slice(offset,offset+6));
  }
  s.geometry.setIndex([...groups[0],...groups[1]]);
  s.geometry.clearGroups();
  s.geometry.addGroup(0,groups[0].length,0);
  s.geometry.addGroup(groups[0].length,groups[1].length,1);
}
type Section = { center: THREE.Vector3; tangent: THREE.Vector3; width: number; depth: number; cross?: THREE.Vector3 };
function fillSurface(s: Surface, section: (t: number) => Section) {
  const positions = s.geometry.attributes.position;
  for (let i = 0; i <= s.rings; i++) {
    const p = section(i / s.rings);
    const cross = p.cross?.clone() ?? v(0, 0, 1);
    cross.addScaledVector(p.tangent, -cross.dot(p.tangent)).normalize();
    const normal = cross.clone().cross(p.tangent).normalize();
    for (let j = 0; j <= s.segments; j++) {
      const angle = j / s.segments * Math.PI * 2;
      const vertex = p.center.clone().addScaledVector(cross, Math.cos(angle) * p.width).addScaledVector(normal, Math.sin(angle) * p.depth);
      positions.setXYZ(i * (s.segments + 1) + j, vertex.x, vertex.y, vertex.z);
    }
  }
  positions.needsUpdate = true;
  s.geometry.computeVertexNormals();
  s.geometry.computeBoundingSphere();
}
function profile(t: number, keys: number[][]) {
  for (let i = 1; i < keys.length; i++) if (t <= keys[i][0]) {
    const u = THREE.MathUtils.smoothstep(t, keys[i - 1][0], keys[i][0]);
    return THREE.MathUtils.lerp(keys[i - 1][1], keys[i][1], u);
  }
  return keys[keys.length - 1][1];
}
function roundedPatch(width: number, height: number, radius: number) {
  const s=new THREE.Shape(),x=-width/2,y=-height/2;
  s.moveTo(x+radius,y);s.lineTo(x+width-radius,y);
  s.quadraticCurveTo(x+width,y,x+width,y+radius);s.lineTo(x+width,y+height-radius);
  s.quadraticCurveTo(x+width,y+height,x+width-radius,y+height);s.lineTo(x+radius,y+height);
  s.quadraticCurveTo(x,y+height,x,y+height-radius);s.lineTo(x,y+radius);
  s.quadraticCurveTo(x,y,x+radius,y);
  const geometry=new THREE.ShapeGeometry(s,10);geometry.rotateX(-Math.PI/2);
  return geometry;
}
function contact(surface: Surface, height: number) {
  surface.geometry.computeBoundingBox();
  surface.geometry.translate(0,height-surface.geometry.boundingBox!.min.y,0);
}

export function createStudio() {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#eee7dd');
  scene.fog = new THREE.Fog('#eee7dd', 12, 28);
  const skin = material('#bf927a', 0.86);
  const shirt = material('#9e4e3b', 0.91);
  const trousers = material('#333d3b', 0.96);
  const hair = material('#34312b', 0.98);
  const sole = material('#e4d7c6', 0.85);
  const shoe = material('#4f5b55', 0.92);
  const graphite = material('#363c39', 0.56);
  const matMaterial = material('#e2d8c9', 0.98);
  const accent = material('#b16a50', 0.89);
  const meshes: THREE.Mesh[] = [];
  const add = (geometry: THREE.BufferGeometry, mat: THREE.Material | THREE.Material[], name: string, parent: THREE.Object3D = scene) => {
    const mesh = new THREE.Mesh(geometry, mat);
    mesh.name = name;
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    parent.add(mesh);
    meshes.push(mesh);
    return mesh;
  };

  const hemisphere = new THREE.HemisphereLight('#fff6e9', '#bab9b2', 2.1);
  scene.add(hemisphere);
  const key = new THREE.DirectionalLight('#fff6e9', 2.6);
  key.position.set(-2.5, 5.5, 3.5);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  Object.assign(key.shadow.camera, { left: -2.7, right: 2.7, top: 2.7, bottom: -2.7, near: 0.1, far: 12 });
  key.shadow.bias = -0.00012;
  key.shadow.normalBias = 0.012;
  key.shadow.radius = 5;
  key.shadow.blurSamples = 12;
  scene.add(key);
  const fill = new THREE.DirectionalLight('#edf3f0', 0.85);
  fill.position.set(2, 3, -4);
  scene.add(fill);

  const floor = add(new THREE.PlaneGeometry(200, 200), material('#eee7dd'), 'studio-floor');
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -0.008;
  floor.castShadow = false;
  const mat = add(new RoundedBoxGeometry(2.64, 0.056, 1.22, 4, 0.027), matMaterial, 'mat');
  mat.position.set(0.42, MAT_TOP - 0.028, 0);
  const matEdge = add(new RoundedBoxGeometry(2.63, 0.018, 1.21, 3, 0.008), material('#b7a591'), 'mat-edge');
  matEdge.position.set(0.42, 0.014, 0);
  const stripe = add(new RoundedBoxGeometry(0.024, 0.002, 0.91, 3, 0.001), accent, 'mat-accent');
  stripe.position.set(1.59, MAT_TOP + 0.001, 0);

  const sensors = [-1, 1].map(side => {
    const zoneMat = material('#c48d73');
    const zone = add(roundedPatch(.30,.24,.035), zoneMat, `palm-zone-${side}`);
    zone.position.set(-0.005, MAT_TOP + 0.0035, side * 0.29);
    zone.castShadow = false;
    const rim = add(roundedPatch(.326,.266,.044), material('#d4b6a0'), `palm-zone-border-${side}`);
    rim.position.set(-0.005, MAT_TOP + 0.0025, side * 0.29);
    rim.castShadow = false;
    return zoneMat;
  });

  const torso = surface(36, 28);
  add(torso.geometry, shirt, 'fitted-shirt');
  const pelvis = surface(16, 24);
  add(pelvis.geometry, trousers, 'waist');
  const neck = surface(10, 16);
  add(neck.geometry, skin, 'neck');
  const head = surface(30, 28);
  add(head.geometry, [skin, hair], 'sculpted-head');
  assignMaterials(head,(i,j)=>{
    const angle = (j + 0.5) / head.segments * Math.PI * 2;
    return i > 8 && (Math.sin(angle) > -0.25 || i > 23) ? 1 : 0;
  });

  const arms = [-1, 1].map(side => {
    const s = surface(48, 16);
    add(s.geometry, [shirt, skin], `continuous-arm-${side}`);
    assignMaterials(s,i=>i<15?0:1);
    return s;
  });
  const legs = [-1, 1].map(side => {
    const s = surface(40, 18);
    add(s.geometry, trousers, `continuous-leg-${side}`);
    return s;
  });

  // Palms are a single tapered closed surface, with a small connected thumb.
  [-1, 1].forEach(side => {
    const palm = surface(18, 16);
    add(palm.geometry, skin, `palm-${side}`);
    fillSurface(palm, t => ({ center: v(0.098 - 0.225 * t, MAT_TOP + 0.028 + 0.045 * Math.exp(-t * 5), side * 0.29), tangent: v(-1, 0, 0), width: profile(t, [[0,0.022],[0.22,0.037],[0.58,0.05],[0.84,0.04],[1,0.001]]), depth: profile(t, [[0,0.027],[0.3,0.028],[0.8,0.020],[1,0.001]]) }));
    const thumb = surface(12, 10);
    add(thumb.geometry, skin, `thumb-${side}`);
    fillSurface(thumb, t => ({ center: v(0.024 - t * 0.083, MAT_TOP + 0.026, side * (0.265 - t * 0.045)), tangent: v(-0.8,0,-side * 0.6), width: profile(t, [[0,.028],[.45,.021],[1,.001]]), depth: profile(t, [[0,.022],[.5,.017],[1,.001]]) }));
    contact(palm,MAT_TOP+.0036);
    contact(thumb,MAT_TOP+.0036);
    return palm;
  });

  // Shoes and toes are fixed. The ankle is the hinge for the rigid plank chain.
  [-1, 1].forEach(side => {
    const footwear = surface(24, 18);
    add(footwear.geometry, [shoe, sole], `trainer-${side}`);
    fillSurface(footwear, t => ({ center: v(1.205 + 0.27 * t, 0.235 - t * 0.172, side * 0.10), tangent: v(0.843,-0.537,0), width: profile(t,[[0,.001],[.16,.058],[.53,.060],[.85,.058],[1,.001]]), depth: profile(t,[[0,.001],[.17,.058],[.5,.051],[.85,.027],[1,.001]]) }));
    assignMaterials(footwear,(_i,j)=>{
      const angle = (j+.5)/footwear.segments*Math.PI*2;
      return Math.sin(angle)<-.45?1:0;
    });
    contact(footwear,MAT_TOP+.0001);
  });

  const phone = new THREE.Group();
  phone.name = 'phone-and-tripod';
  phone.position.set(-1.20, 0, -0.44);
  phone.rotation.y = 1.22 + Math.PI;
  scene.add(phone);
  const caseMesh = add(new RoundedBoxGeometry(.18,.345,.028,4,.014), graphite, 'phone-case', phone);
  caseMesh.position.y=.66;
  const screen = add(new RoundedBoxGeometry(.159,.315,.004,3,.0018), material('#202d2b',.3),'phone-screen',phone);
  screen.position.set(0,.66,.017);
  const lens = add(new THREE.CircleGeometry(.009,16),material('#879e99',.2),'phone-lens',phone);
  lens.position.set(.048,.794,-.015);
  lens.rotation.y=Math.PI;
  const stem=add(new THREE.CylinderGeometry(.009,.012,.37,12),graphite,'tripod-stem',phone);
  stem.position.y=.315;
  for (let i=0;i<3;i++) {
    const a=i*Math.PI*2/3;
    const end=v(Math.cos(a)*.15,.012,Math.sin(a)*.15), start=v(0,.21,0);
    const leg=add(new THREE.CylinderGeometry(.008,.011,start.distanceTo(end),10),graphite,`tripod-leg-${i}`,phone);
    leg.position.copy(start).add(end).multiplyScalar(.5);
    leg.quaternion.setFromUnitVectors(UP,end.sub(start).normalize());
  }

  const bounds = new THREE.Box3(v(-1.25,0,-.91),v(1.77,1.0,.65));
  const camera = new THREE.PerspectiveCamera(32,1,.05,60);
  const target = v(.25,.33,-.035);
  const framingPoints: THREE.Vector3[] = [];
  function compose(aspect: number, yaw=INITIAL_YAW, pitch=INITIAL_PITCH) {
    camera.aspect=aspect;
    const direction=v(Math.cos(yaw)*Math.cos(pitch),Math.sin(pitch),Math.sin(yaw)*Math.cos(pitch));
    const right=UP.clone().cross(direction).normalize();
    const up=direction.clone().cross(right).normalize();
    const tangent=Math.tan(THREE.MathUtils.degToRad(camera.fov/2));
    let distance=3;
    for(const vertex of framingPoints) {
      const p=vertex.clone().sub(target);
      distance=Math.max(distance,p.dot(direction)+Math.abs(p.dot(right))/(tangent*aspect*.84),p.dot(direction)+Math.abs(p.dot(up))/(tangent*.80));
    }
    camera.position.copy(target).addScaledVector(direction,distance);
    camera.lookAt(target);
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();
  }

  function update(depth: number) {
    const pose=poseAt(depth);
    fillSurface(torso,t=>({center:pose.point(-.065+t*.70),tangent:pose.axis,width:profile(t,[[0,.06],[.10,.192],[.23,.204],[.43,.174],[.70,.142],[.90,.149],[1,.143]]),depth:profile(t,[[0,.06],[.13,.106],[.32,.117],[.62,.087],[.9,.099],[1,.085]])}));
    fillSurface(pelvis,t=>({center:pose.point(.54+t*.21),tangent:pose.axis,width:profile(t,[[0,.146],[.4,.16],[.7,.145],[1,.06]]),depth:profile(t,[[0,.087],[.4,.098],[1,.07]])}));
    fillSurface(neck,t=>({center:pose.point(-.04-t*.12,.021),tangent:pose.axis.clone().negate(),width:profile(t,[[0,.065],[.5,.055],[1,.05]]),depth:.055}));
    fillSurface(head,t=>({center:pose.point(-.11-t*.25,.025),tangent:pose.axis.clone().negate(),cross:v(0,0,-1),width:profile(t,[[0,.043],[.18,.075],[.42,.093],[.7,.091],[.9,.052],[1,.001]]),depth:profile(t,[[0,.06],[.20,.09],[.46,.119],[.7,.11],[.9,.068],[1,.001]])}));
    pose.sides.forEach((side,i)=>{
      const { shoulder,elbow,wrist,hip,ankle }=side;
      // Tangent-continuous curve passes through the exact IK elbow and wrist.
      const curve=new THREE.CatmullRomCurve3([
        shoulder.clone().add(v(0,0,-side.side*.095)),
        shoulder,
        shoulder.clone().lerp(elbow,.32),
        shoulder.clone().lerp(elbow,.80),
        elbow,
        elbow.clone().lerp(wrist,.22),
        elbow.clone().lerp(wrist,.72),
        wrist.clone().add(v(-.012,-.012,0)),
      ],false,'centripetal');
      fillSurface(arms[i],t=>({center:curve.getPoint(t),tangent:curve.getTangent(t),cross:pose.axis,width:profile(t,[[0,.040],[.13,.079],[.27,.070],[.5,.048],[.68,.053],[.86,.039],[1,.027]]),depth:profile(t,[[0,.040],[.13,.079],[.3,.067],[.5,.048],[.7,.053],[1,.027]])}));
      fillSurface(legs[i],t=>({center:hip.clone().lerp(ankle,t).addScaledVector(pose.axis,-.055*(1-THREE.MathUtils.smoothstep(t,0,.2))).add(v(0,0,-side.side*.015*(1-THREE.MathUtils.smoothstep(t,0,.2)))),tangent:pose.axis,width:profile(t,[[0,.062],[.13,.100],[.36,.077],[.5,.059],[.66,.065],[.82,.046],[1,.030]]),depth:profile(t,[[0,.060],[.15,.100],[.48,.060],[.7,.065],[1,.029]])}));
    });
    sensors.forEach(mat=>{mat.color.set('#c9957d').lerp(new THREE.Color('#b66f55'),depth*.65);mat.emissive.set('#a65b41');mat.emissiveIntensity=.012+depth*.035;});
    scene.updateMatrixWorld(true);
    return pose;
  }
  for(const depth of [0,1]) {
    update(depth);
    for(const mesh of meshes) {
      if(mesh===floor) continue;
      const p=mesh.geometry.attributes.position;
      for(let i=0;i<p.count;i+=3) framingPoints.push(v().fromBufferAttribute(p,i).applyMatrix4(mesh.matrixWorld));
    }
  }
  update(0);
  compose(1);
  return {scene,camera,compose,update,meshes,bounds,dispose(){
    const geometries=new Set<THREE.BufferGeometry>(),materials=new Set<THREE.Material>();
    meshes.forEach(mesh=>{geometries.add(mesh.geometry);(Array.isArray(mesh.material)?mesh.material:[mesh.material]).forEach(m=>materials.add(m));});
    geometries.forEach(g=>g.dispose());materials.forEach(m=>m.dispose());
    key.shadow.map?.dispose();key.shadow.mapPass?.dispose();
  }};
}
