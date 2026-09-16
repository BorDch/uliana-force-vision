"""Render the actual exported Three.js meshes/cameras, without a browser.
Blender lighting approximates the web studio; this is not a WebGL screenshot.
Usage: blender -b --python scripts/render-scene-checks.py -- scene-checks/desktop-top.json
"""
import bpy, json, math, sys, os
from pathlib import Path
from mathutils import Vector, Quaternion

for filename in sys.argv[sys.argv.index('--')+1:]:
    source = Path(filename)
    data = json.loads(source.read_text())
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.render.resolution_x = data['width']
    scene.render.resolution_y = data['height']
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = 'AgX'
    scene.world = bpy.data.worlds.new('Studio fill')
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value = (.75,.73,.69,1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value = 1.0

    for item in data['meshes']:
        mesh = bpy.data.meshes.new(item['name'])
        idx = item['indices']
        faces = [idx[i:i+3] for i in range(0,len(idx),3)]
        mesh.from_pydata(item['vertices'],[],faces)
        mesh.update()
        obj = bpy.data.objects.new(item['name'],mesh)
        scene.collection.objects.link(obj)
        for spec in item['materials']:
            mat = bpy.data.materials.new(item['name'])
            mat.use_nodes = True
            p = mat.node_tree.nodes.get('Principled BSDF')
            p.inputs['Base Color'].default_value=(*spec['color'],1)
            p.inputs['Roughness'].default_value=spec['roughness']
            p.inputs['Metallic'].default_value=spec['metalness']
            mesh.materials.append(mat)
        for polygon in mesh.polygons: polygon.use_smooth=True
        for group in item['groups']:
            for polygon in mesh.polygons[group['start']//3:(group['start']+group['count'])//3]:
                polygon.material_index=group['materialIndex']

    cam = bpy.data.cameras.new('Exact Three camera')
    obj = bpy.data.objects.new('Camera',cam)
    scene.collection.objects.link(obj)
    obj.location=data['camera']['position']
    x,y,z,w=data['camera']['quaternion']
    obj.rotation_mode='QUATERNION'
    obj.rotation_quaternion=Quaternion((w,x,y,z))
    cam.sensor_fit='VERTICAL'
    cam.sensor_height=24
    cam.lens=12/math.tan(math.radians(data['camera']['fov']/2))
    scene.camera=obj

    for name,location,power,size,color in [
        ('Key',(-2.5,5.5,3.5),600,4,(1,.94,.85)),
        ('Fill',(2,3,-4),220,4,(.85,.93,1)),
    ]:
        lamp=bpy.data.lights.new(name,'AREA')
        lamp.energy=power;lamp.shape='DISK';lamp.size=size;lamp.color=color
        obj=bpy.data.objects.new(name,lamp);scene.collection.objects.link(obj)
        obj.location=location
        obj.rotation_euler=(Vector((.3,.2,0))-obj.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(source.with_suffix('.png').resolve())
    if os.environ.get('ULIANA_RENDER_ANIMATION') == '1':
        frames=json.loads((source.parent/'animation.json').read_text())
        output=source.parent/'frames'
        output.mkdir(exist_ok=True)
        scene.render.resolution_x=480
        scene.render.resolution_y=422
        scene.cycles.samples=8
        scene.render.image_settings.file_format='PNG'
        for number,frame in enumerate(frames):
            for name,coordinates in frame.items():
                mesh=bpy.data.objects[name].data
                mesh.vertices.foreach_set('co',coordinates)
                mesh.update()
            scene.render.filepath=str((output/f'{number:04d}.png').resolve())
            bpy.ops.render.render(write_still=True)
    else:
        bpy.ops.render.render(write_still=True)
