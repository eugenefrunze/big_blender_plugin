from ctypes import cast
from email.mime import base
import pathlib


import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
import gpu
from gpu_extras.batch import batch_for_shader
import bgl
import blf 
from mathutils import Vector

from . import data_types
from . import utils
from .utils import get_edges_of_selected_verts_2, get_object_bounds_coords, get_bounder_vertices, set_parent, \
get_vector_from_coordinates, get_vector_center, select_none, set_active, set_boundings_for_object, get_bounder_face

#---------------------------------------------------------------------------------------------------
# wall builder operators
#---------------------------------------------------------------------------------------------------

class CustomersBaseHandler(bpy.types.Operator):
    bl_idname = 'scene.customers_base_handler'
    bl_label = 'customers_base_handler'
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context: bpy.types.Context):
        utils.get_customers_info()
        # print(data_types.customers_json)
        print('--------------------------')
        for idx, item in enumerate(data_types.customers_json):
            if len(data_types.customers_json) > len(context.scene.customers_data):
                context.scene.customers_data.add()
            print(len(context.scene.customers_data))
            for key in item.keys():
                try:
                    if item[key]:
                        context.scene.customers_data[idx][key] = int(item[key])
                except ValueError:
                    if item[key]:
                        context.scene.customers_data[idx][key] = str(item[key])
            print('--------------------------')
        return {'FINISHED'}
        
#end of customers base handler operator ------------------------------------------------------------


class WallBuilder(bpy.types.Operator):
    bl_idname = 'object.wall_builder'
    bl_label = 'GANERATOR HANDLER'
    bl_options = {'REGISTER', 'UNDO'}

    is_reset: bpy.props.BoolProperty()

    wall_profile_curve: bpy.types.Object

    handler1 = 0

    # wallbuilder custom methods from here
    def set_customer_preset(self, context):
        obj_converted = context.object
        if obj_converted.wb_props.object_type == 'WALL':
            for customer in data_types.customers_json:
                if customer['ucm_id'] == obj_converted.wb_props.customer:
                    obj_converted.wb_props.height = float(customer['wall_height']) / 1000
                    obj_converted.wb_props.opening_top_offset = float(customer['windows_top']) / 1000
                    if self.is_inner_wall:
                        obj_converted.wb_props.thickness = float(customer['wall_in_thickness']) / 1000
                    else:
                        obj_converted.wb_props.thickness = float(customer['wall_out_thickness']) / 1000
        elif obj_converted.wb_props.object_type == 'FLOOR':
            for customer in data_types.customers_json:
                if customer['ucm_id'] == obj_converted.wb_props.customer:
                    obj_converted.wb_props.height = float(customer['ceiling']) / 1000

    def set_wall_position(self, context):
        if context.active_object.wb_props.object_type == 'WALL' and \
            context.active_object.type == 'CURVE':
            height: float
            thickness: float
            if self.__class__.__name__ == 'WBProps':
                height = self.height
                thickness = self.thickness
            else:
                height = context.object.wb_props.height
                thickness = context.object.wb_props.thickness

            # getting references for all points of the wallshape
            points = []
            #check if taper object created (or the wall is just a curve at the moment)
            if context.active_object.wb_props.wall_profile_curve != None:
                for point in context.active_object.data.bevel_object.data.splines[0].points:
                    points.append(point)

            #if points is empty, then the wall is just a curve at the moment
            if len(points) > 0:
                if context.object.wb_props.position == 'INSIDE':
                    # 1st point
                    points[0].co[0] = 0
                    points[0].co[1] = height
                    # 2nd point
                    points[1].co[0] = thickness
                    points[1].co[1] = height
                    # 3rd point
                    points[2].co[0] = thickness
                    points[2].co[1] = 0
                    # 4th point
                    points[3].co[0] = 0
                    points[3].co[1] = 0

                elif context.object.wb_props.position == 'CENTER':
                    # 1st point
                    points[0].co[0] = -(thickness / 2)
                    points[0].co[1] = height
                    # 2nd point
                    points[1].co[0] = thickness / 2
                    points[1].co[1] = height
                    # 3rd point
                    points[2].co[0] = thickness / 2
                    points[2].co[1] = 0
                    # 4th point
                    points[3].co[0] = -(thickness / 2)
                    points[3].co[1] = 0

                elif context.object.wb_props.position == 'OUTSIDE':
                    # 1st point
                    points[0].co[0] = -thickness
                    points[0].co[1] = height
                    # 2nd point
                    points[1].co[0] = 0
                    points[1].co[1] = height
                    # 3rd point
                    points[2].co[0] = 0
                    points[2].co[1] = 0
                    # 4th point
                    points[3].co[0] = -thickness
                    points[3].co[1] = 0

    def generate_object(self, context) -> list:
        obj = context.object
        wb_props = obj.wb_props
        obj_conv_collection = obj.users_collection[0]
        if obj.wb_props.object_type == 'WALL':
            # setting object base parameters
            obj.data.dimensions = '2D'
            obj.name = 'wb_wall_{0}_{1}'.format('inner' if wb_props.is_inner_wall else 'outer', wb_props.level)
            # geometry nodes modifier
            geom_nodes_mod = bpy.context.object.modifiers.new("wb_geom_nodes", 'NODES')
            node_group = geom_nodes_mod.node_group
            node_group.name = '{}_geom_nodes_node_group'.format(obj.name)
            # creating nodes
            nd_input = node_group.nodes['Group Input']
            nd_output = node_group.nodes['Group Output']
            nd_set_shade_smooth = node_group.nodes.new(type="GeometryNodeSetShadeSmooth")
            nd_bool_openings = node_group.nodes.new(type="GeometryNodeMeshBoolean")
            # setting params
            nd_output.location = (500, 0)
            nd_set_shade_smooth.inputs[2].default_value = False
            nd_bool_openings.name = 'mrBoolshit'
            nd_bool_openings.location = (300, -100)
            # create links
            nd_input.outputs.clear()
            nd_output.outputs.clear()
            utils.node_group_link(node_group, nd_input.outputs['Geometry'], nd_set_shade_smooth.inputs['Geometry'])
            utils.node_group_link(node_group, nd_set_shade_smooth.outputs['Geometry'],
                                  nd_bool_openings.inputs['Mesh 1'])
            utils.node_group_link(node_group, nd_output.inputs['Geometry'], nd_bool_openings.outputs['Mesh'])
            # shape curve from here
            bpy.ops.curve.simple(align='WORLD', location=(0, 0, 0), rotation=(0, 0, 0), Simple_Type='Rectangle',
                                 Simple_width=1, Simple_length=0, use_cyclic_u=True)
            obj_profile = context.object
            obj.wb_props.wall_profile_curve = obj_profile
            obj.data.use_fill_caps = True
            obj_profile.name = f'{obj.name}_taper'
            obj_profile_data = obj_profile.data
            obj_profile_data.fill_mode = 'NONE'
            bpy.ops.curve.spline_type_set(type='POLY')
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.collection.objects_remove_active()
            bpy.ops.object.select_all(action='DESELECT')
            context.view_layer.objects.active = obj
            obj.data.bevel_mode = 'OBJECT'
            obj.data.bevel_object = obj_profile
            # set the sizes of newly generated wall
            self.set_wall_position(context)
            obj.wb_props.is_converted = True

        elif obj.wb_props.object_type == 'OPENING':
            pass

        elif obj.wb_props.object_type == 'FLOOR':
            # setting object base parameters
            obj.data.bevel_mode = 'ROUND'
            obj.data.extrude = obj.wb_props.height / 2
            obj.data.fill_mode = 'BOTH'
            obj.name = 'wb_floor_{0}'.format(wb_props.level)
            # geometry nodes modifier
            geom_nodes_mod = bpy.context.object.modifiers.new("wb_geom_nodes", 'NODES')
            node_group = geom_nodes_mod.node_group
            node_group.name = '{}_geom_nodes_node_group'.format(obj.name)
            # creating nodes
            nd_input = node_group.nodes['Group Input']
            nd_output = node_group.nodes['Group Output']
            nd_set_shade_smooth = node_group.nodes.new(type="GeometryNodeSetShadeSmooth")
            # setting params
            nd_output.location = (500, 0)
            nd_set_shade_smooth.inputs[2].default_value = False
            # create links
            utils.node_group_link(node_group, nd_input.outputs['Geometry'], nd_set_shade_smooth.inputs['Geometry'])
            utils.node_group_link(node_group, nd_output.inputs['Geometry'], nd_set_shade_smooth.outputs['Geometry'])
            # set object as converted in wb_props
            obj.wb_props.is_converted = True

    def reset_object(self, obj: bpy.types.Object):
        if obj.wb_props.object_type == 'WALL':
            # remove the geom nodes modifier
            try:
                geom_nodes_mod = obj.modifiers['wb_geom_nodes']
            except KeyError:
                print('OBJECT HAD NO wb_geom_nodes MODIFIER')
            else:
                obj.modifiers.remove(geom_nodes_mod)
            # deleting the profile curve
            bpy.ops.object.mode_set(mode='OBJECT')
            obj.data.bevel_object = None
            bpy.ops.object.select_all(action='DESELECT')
            try:
                if obj.wb_props.wall_profile_curve:
                    obj.wb_props.wall_profile_curve.select_set(True)
            except RuntimeError:
                pass
            else:
                bpy.ops.object.delete()
            obj.select_set(True)
            obj.wb_props.wall_profile_curve = None
            # clearing the fill mode if obj previously was a floor
            obj.data.fill_mode = 'NONE'
            # clearing the openings list
            obj.openings.clear()
            obj.opening_index = -1
            # setting the object is not converted
            obj.wb_props.is_converted = False

        elif obj.wb_props.object_type == 'FLOOR':
            # if object has geom nodes modifier (ex. prev was floor)
            try:
                geom_nodes_mod = obj.modifiers['wb_geom_nodes']
            except KeyError:
                print('OBJECT HAD NO wb_geom_nodes MODIFIER')
            else:
                obj.modifiers.remove(geom_nodes_mod)
            # setting the spline parameters
            obj.data.extrude = 0
            obj.data.fill_mode = 'NONE'
            obj.wb_props.is_converted = False

    # wallbuilder class methods here
    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'CURVE'

    def execute(self, context):
        obj = context.object
        if obj.wb_props.is_converted:
            self.reset_object(obj)
            self.report({'INFO'}, 'OBJECT HAS BEEN RESET')
            return {'FINISHED'}
        else:
            self.generate_object(context)
            self.report({'INFO'}, 'OBJECT GENERATED')
            return {'FINISHED'}

#end of wall builder operator ----------------------------------------------------------------------


class OpeningsHandler(bpy.types.Operator):
    bl_idname = "object.opnenings_adder"
    bl_label = "mrlist"

    action: bpy.props.EnumProperty(
        items=(
            ('REMOVE', "Remove", ""),
            ('ADD', "Add", ""),
            ('UP', 'Up', ''),
            ('DOWN', 'Down', '')))

    nd_loc = [0, -200]

    def add_opening_to_geom_nodes(self, construction, opening, location):
        '''construction - actual building element to add openings to'''
        try:
            modifier = construction.modifiers['wb_geom_nodes']
        except KeyError:
            print('CONSTRUCTION OBJECT HAS NO GEOM NODES MODIFIER')
        else:
            # getting node group if modif exists
            node_group = modifier.node_group
            # adding opening as object info node
            info_node = node_group.nodes.new(type="GeometryNodeObjectInfo")
            # setting the parameters
            info_node.inputs[0].default_value = opening
            info_node.transform_space = 'RELATIVE'
            info_node.location = location
            # create links
            utils.node_group_link(node_group, info_node.outputs['Geometry'],
                                  node_group.nodes['mrBoolshit'].inputs['Mesh 2'])
            return info_node

    def remove_opening_from_geom_nodes(self, construction, info_obj: bpy.types.Object):
        '''construction - actual building element to remove opening from, info_obj - actual opening 
        object from the scene'''
        try:
            modifier = construction.modifiers['wb_geom_nodes']
        except KeyError:
            print('CONSTRUCTION OBJECT HAS NO GEOM NODES MODIFIER')
        else:
            node_group = modifier.node_group
            nodes = node_group.nodes
            # nodes.remove(construction.openings.obj_id)
            for node in nodes:
                if node.type == 'OBJECT_INFO' and node.inputs[0].default_value == info_obj:
                    nodes.remove(node)
                    nd_bool_openings = node_group.nodes['mrBoolshit']
                    nd_output = node_group.nodes['Group Output']
                    utils.node_group_link(node_group, nd_output.inputs['Geometry'], nd_bool_openings.outputs['Mesh'])

    def invoke(self, context, event):
        """nd_loc - initial location for the new obj info node"""
        obj = context.object
        idx = obj.opening_index
        try:
            item = obj.openings[idx]
        except IndexError:
            pass
        else:
            if self.action == 'DOWN' and idx < len(obj.openings) - 1:
                item_next = obj.openings[idx + 1].obj.name
                obj.openings.move(idx, idx + 1)
                obj.opening_index += 1
                info = 'Item "%s" moved to position %d' % (item.obj.name, obj.opening_index + 1)
                self.report({'INFO'}, info)

            elif self.action == 'UP' and idx >= 1:
                item_prev = obj.openings[idx - 1].obj.name
                obj.openings.move(idx, idx - 1)
                obj.opening_index -= 1
                info = 'Item "%s" moved to position %d' % (item.obj.name, obj.opening_index + 1)
                self.report({'INFO'}, info)

            elif self.action == 'REMOVE':
                obj.opening_index -= 1
                # deleting object from geom nodes modifier and refreshing geom nodes modifier
                self.remove_opening_from_geom_nodes(obj, obj.openings[idx].obj)
                self.nd_loc[1] += 200
                # removing opening from construction object
                obj.openings.remove(idx)

        if self.action == 'ADD':
            obj.select_set(False)
            
            sel_objects = context.selected_objects.copy()
            bpy.ops.object.select_all(action='DESELECT')
            for object in sel_objects:
                # check if opening is a duplicate
                if len(obj.openings) > 0:
                    for opening in obj.openings:
                        if object == opening.obj:
                            self.report({'WARNING'}, 'This object is already in the openings')
                            return {'CANCELLED'}
                # create new opening
                item = obj.openings.add()
                item.obj = object
                item.obj_id = len(obj.openings)
                obj.opening_index = len(obj.openings) - 1
                # putting the object to geom nodes modif
                self.add_opening_to_geom_nodes(obj, object, self.nd_loc)
                self.nd_loc[1] -= 200
                print(self.nd_loc[1])
                print(f'OPENING ADDED: {item.obj.name}')
        return {'FINISHED'}

#end of openings handler operator ------------------------------------------------------------------


class OpeningsAttacher(bpy.types.Operator):
    bl_idname = 'object.openings_attacher'
    bl_label = 'attach_openings'
    
    action: bpy.props.StringProperty()
    
    
    def execute(self, context: bpy.types.Context):
        obj: bpy.types.Object = bpy.context.object
        
        #set the action, depending on the presence of openings
        if len(obj.children) > 0: self.action = 'DETACH'
        else: self.action = 'ATTACH'
                
        print(len(obj.openings))
            
        if self.action == 'ATTACH':
            select_none()
            ctx_temp = context.copy()
            for opening in obj.openings:
                ctx_temp['selected_editable_objects'].append(opening.obj)
                ctx_temp['selected_objects'].append(opening.obj)
            bpy.ops.object.parent_set(ctx_temp, keep_transform=True)
            self.report({'INFO'}, 'ALL OPENINGS HAVE BEEN ATTACHED')
        if self.action == 'DETACH':
            select_none()
            for opening in obj.openings:
                opening.obj.select_set(True)
            obj.select_set(True)
            bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
            self.report({'INFO'}, 'ALL OPENINGS HAVE BEEN DETACHED')
        
        return {'FINISHED'}
    
class OpeningsAligner(bpy.types.Operator):
    bl_idname = 'object.openings_aligner'
    bl_label = 'align_openings'
    
    def execute(self, context: bpy.types.Object):
        obj: bpy.types.Object = context.object
        for opening in obj.openings:
            if opening.obj.wb_props.helper_type == 'WINDOW':
                bounds = get_object_bounds_coords(opening.obj, 'WORLD')
                opening.obj.location[2] = (obj.location[2] + obj.wb_props.opening_top_offset) - (bounds[2] - opening.obj.location[2])
            
        self.report({'INFO'}, 'Openings aligned')
        return {'FINISHED'}

#---------------------------------------------------------------------------------------------------
# building assembler operator
#---------------------------------------------------------------------------------------------------

class BuildingAssembler(bpy.types.Operator):
    bl_idname = 'object.building_assembler'
    bl_label = 'ASSEMBLE THE BUILDING'
    bl_options = {'REGISTER', 'UNDO'}

    def generate_floor(self, objs: dict, level: str, init_loc, elevation):
        '''elevation - maximum z point of the prev level or previous placed object in the current
                level. It updates every time when the next object or level positioned above the previous'''
        # max height of outside walls
        max_wall_height = 0
        floor_added: bool = False
        # setting objs locations and calculating elevation
        for group in objs[level]:
            for obj in objs[level][group]:
                wb_props = obj.wb_props
                if wb_props.object_type == 'FLOOR':
                    obj.location = (init_loc[0], init_loc[1], elevation + (wb_props.height / 2))
                    elevation += wb_props.height
                    floor_added = True
                elif wb_props.object_type == 'WALL':
                    if floor_added:
                        obj.location = (init_loc[0], init_loc[1], elevation)
                    else:
                        floor_height = objs[level]['floors'][0].wb_props.height
                        obj.location = (init_loc[0], init_loc[1], elevation + floor_height)
                    if wb_props.height > max_wall_height:
                        max_wall_height = wb_props.height
        elevation += max_wall_height
        # getting the key of the next level
        objs_temp = list(objs)
        try:
            next_level = objs_temp[objs_temp.index(level) + 1]
        except (ValueError, IndexError):
            next_level = None

        return {'next_level': next_level, 'elevation': elevation}

    def assemble_building(self, context):
        # filling the all objs holder. Floors must be the first in the dictionary as they increase
        # the global elevation to use it later for the walls of the same level

        # generate objects dictionary
        objs = {}
        for level in data_types.levels:
            objs[level[0]] = {'floors': [], 'outer_walls': [], 'inner_walls': []}
        # filling the objects dictionary
        wb_objects = context.scene.wb_props.plans_collection.objects
        for obj in wb_objects:
            wb_props = obj.wb_props
            for level in data_types.levels:
                if wb_props.level == level[0] and wb_props.object_type == 'WALL' and not wb_props.is_inner_wall:
                    objs[level[0]]['outer_walls'].append(obj)
                if wb_props.level == level[0] and wb_props.object_type == 'WALL' and wb_props.is_inner_wall:
                    objs[level[0]]['inner_walls'].append(obj)
                if wb_props.level == level[0] and wb_props.object_type == 'FLOOR':
                    objs[level[0]]['floors'].append(obj)

        # ASSEMBLING THE OBJECTS (WORKS ONLY FOR MAXIMUM 4-LEVEL ON-GROUND BUILDING (WITHOUT CELLAR))
        # getting EG (1st floor) wall position as
        init_loc = context.scene.wb_props.alignment_object.location
        EG_level_max_height = max(
            [a.wb_props.height for a in objs['EG']['outer_walls']])  # the highest wall on EG (1st fl)
        # assembling EG (1st floor)
        for group in objs['EG']:
            for obj in objs['EG'][group]:
                obj.location = init_loc
        # assembling OG (2nd floor)
        OG_data = self.generate_floor(objs, 'OG', init_loc, EG_level_max_height)
        # assembling THIRD (3rd floor)
        THIRD_data = self.generate_floor(objs, OG_data['next_level'], init_loc, OG_data['elevation'])
        # assembling THIRD (3rd floor)
        DG_data = self.generate_floor(objs, THIRD_data['next_level'], init_loc, THIRD_data['elevation'])

    def execute(self, context):
        # print(self.generate_first_floor(context))
        self.assemble_building(context)
        info = 'BUILDING HAS ASSEMBLED'
        self.report({'INFO'}, info)
        return {'FINISHED'}
    
# building assembler operator ----------------------------------------------------------------------


class SnappingCopyHandler(bpy.types.Operator):
    bl_idname = 'object.snapping_copy_handler'
    bl_label = 'snapping_copy_handler'
    
    action: bpy.props.StringProperty()
    
    @classmethod
    def poll(cls, context):
        return context.object in context.selected_objects
    
    def execute(self, context: bpy.types.Context):
        base_wall = context.object
        cast_obj = None
        if self.action == 'ADD':
            #create copy of wall object
            bpy.ops.object.duplicate_move(OBJECT_OT_duplicate={"linked":False, "mode":'TRANSLATION'},
            TRANSFORM_OT_translate={"value":(0, 0, 0), "orient_axis_ortho":'X',
                                    "orient_type":'GLOBAL', "orient_matrix":((0, 0, 0), (0, 0, 0), (0, 0, 0)),
                                    "orient_matrix_type":'GLOBAL', "constraint_axis":(False, False, False),})    
            bpy.ops.object.convert(target='MESH')
            cast_obj = context.object
            base_wall.wb_props.snapping_cast = cast_obj
            cast_obj.name = base_wall.name + '_CAST'
            set_active(base_wall)
            select_none()
            cast_obj.select_set(True)
            base_wall.select_set(True)
            bpy.ops.object.parent_set(keep_transform=True)
            cast_obj.display_type = 'WIRE'
            cast_obj.wb_props.object_type = 'HELPER'
            # bpy.ops.collection.objects_remove_active()
            cast_obj.hide_select = True
            base_wall.select_set(True)
        elif self.action == 'REMOVE':
            select_none()
            base_wall.wb_props.snapping_cast.hide_select = False
            #link cast to walls collection
            try:
                base_wall.users_collection[0].objects.link(base_wall.wb_props.snapping_cast)
            except RuntimeError:
                pass
            set_active(base_wall.wb_props.snapping_cast)
            base_wall.wb_props.snapping_cast.select_set(True)
            bpy.ops.object.delete()
            base_wall.wb_props.snapping_cast = None
            set_active(base_wall)
            
        self.report({'INFO'}, 'Snapping copy hander has finished')
        return {'FINISHED'}


#---------------------------------------------------------------------------------------------------
# tools operators
#---------------------------------------------------------------------------------------------------

class ExtraCurvesEnabler(bpy.types.Operator):
    bl_idname = 'custom.extracurvesenabler'
    bl_label = 'enable curve extra'
    bl_options = {'REGISTER', 'UNDO'}
    

    def execute(self, context):
        bpy.ops.preferences.addon_enable(module="add_curve_extra_objects")

        self.report({'INFO'}, '"Add Curve: Extra Objects" modifier enabled')
        return {'FINISHED'}


class CurveAdder(bpy.types.Operator):
    bl_idname = 'object.curve_adder'
    bl_label = 'ADD CURVE'
    bl_options = {'REGISTER', 'UNDO'}

    curve_type: bpy.props.StringProperty(
        default=data_types.fast_objects_types[0][0]
    )

    def execute(self, context):
        if self.curve_type == 'RECTANGLE':
            curve = utils.curve_create_rectangle(self, context)
        elif self.curve_type == 'LINE':
            #adding line
            # bpy.ops.curve.simple(align='WORLD', location=(0, 0, 0), rotation=(0, 0, 0), Simple_Type='Line', shape='3D', use_cyclic_u=False)
            # bpy.ops.transform.resize(value=(1, 1, 0))
            # bpy.ops.curve.spline_type_set(type='POLY')
            # bpy.ops.object.mode_set(mode='OBJECT')
            # bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS', center='MEDIAN')

            curve = utils.curve_create_line(self, context, (0, 0, 0, 1), (3, 0, 0, 1))
            print(curve.name)

        return {'FINISHED'}


class BoundingsHaldler(bpy.types.Operator):
    bl_idname = 'object.openings_bounds_creator'
    bl_label = 'CREATE BOUNDS'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'MESH'

    def execute(self, context):
        obj = context.object
        #check if the object is not of bounding type
        if obj.props.type == 'BOUNDING':
            self.report({'WARNING'}, 'The object is itself a bounding!')
            return {'CANCELLED'}

        if obj.wb_props.bounding_object == None:
            set_boundings_for_object(obj, context, True)
            
            self.report({'INFO'}, 'Bounding object created successfully')
            return {'FINISHED'}
        else:
            # cheking if object has dead (deleted) bounding object
            try:
                obj.wb_props.bounding_object.select_set(True)
            except RuntimeError as err:
                print(err, 'Reason: Object had dead bounding object. Created a new one')
                self.report({'INFO'}, 'Object had dead bounding object. Created a new one')
                obj.wb_props.bounding_object = None
                set_boundings_for_object(obj, context, True)
                return {'FINISHED'}
            else:
                print('Object already has a bounding object')
                obj.wb_props.bounding_object.select_set(False)
                self.report({'INFO'}, 'Object already has a bounding object')
                return {'FINISHED'}


class FBXLibraryImporter(bpy.types.Operator):

    bl_idname = 'scene.fbx_library_importer'
    bl_label = 'IMPORT ALL FBX'
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        abspath = bpy.path.abspath(context.scene.props.library_fbx_import_path)
        # print(abspath)
        import_path = pathlib.Path(abspath)
        # print(import_path)

        for import_fpath in import_path.glob('*.fbx'):
            print(str(import_fpath))
            bpy.ops.import_scene.fbx(filepath=str(import_fpath))

        return {'FINISHED'}


class OT_TestModalOperator(bpy.types.Operator):
    bl_idname = 'object.test_modal_operator'
    bl_label = 'Test Modal Operator'
    bl_options = {'REGISTER'}


    crap: bpy.props.StringProperty()
    crap2: bpy.props.StringProperty()

    # def __init__(self):
    #     self.test1 = 0
    #     self.test2 = 0

    def invoke(self, context, event: bpy.types.Event):
        self.crap = 'ZZZ'
        self.crap2 = 'ZZZ'
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

        
        # self.crap = event.type
        # self.crap2 = event.ctrl
        # return self.execute(context)
        # return {'PASS_THROUGH'}

    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        # print(event.type)
        if event.type == 'MOUSEMOVE':
            print(f'MOUSEMOVE: {event.mouse_x}', f'{event.mouse_y}')
        
        elif event.type == 'LEFTMOUSE':
            print(f'LEFT {event.value} at {event.mouse_x}, {event.mouse_y}')

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            print(f'{event.type} {event.value} -- STOPPING')
            # return {'FINISHED'}
            return self.execute(context)

        return {'PASS_THROUGH'}
        

    def execute(self, context):
        self.report({'INFO'}, f'{self.bl_idname} EXECUTED {self.crap} {self.crap2}')
        return {'FINISHED'} 


class OT_TestGPUDrawer(bpy.types.Operator):
    bl_idname = 'object.gpu_drawer'
    bl_label = 'draw gpu'
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'MESH'

    def draw_line_3d(color, start, end):
        shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'LINES', {"pos": [start, end]})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)
    
    def draw_callback_3d(self, operator, context):
        vert1 = (context.object.matrix_world @ context.object.data.vertices[0].co) + Vector((0.2, 0.2, 0))
        vert2 = (context.object.matrix_world @ context.object.data.vertices[1].co) + Vector((0.2, 0.2, 0))

        pos1 = (context.object.matrix_world @ context.object.data.vertices[0].co)
        pos2 = (context.object.matrix_world @ context.object.data.vertices[0].co) + Vector((0.4, 0.4, 0))

        pos3 = (context.object.matrix_world @ context.object.data.vertices[1].co)

        pos4 = (context.object.matrix_world @ context.object.data.vertices[1].co) + Vector((0.4, 0.4, 0))

        bgl.glEnable(bgl.GL_BLEND)
        bgl.glEnable(bgl.GL_LINE_SMOOTH)
        bgl.glEnable(bgl.GL_DEPTH_TEST)

        #draw line 1
        shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'LINES', {"pos": [vert1, vert2]})
        shader.bind()
        shader.uniform_float("color", (0.0, 1.0, 0.0, 0.7))
        batch.draw(shader)

        #draw line 2
        shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'LINES', {"pos": [pos1, pos2]})
        shader.bind()
        shader.uniform_float("color", (0.0, 1.0, 0.0, 0.7))
        batch.draw(shader)

        #draw line 3
        shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'LINES', {"pos": [pos3, pos4]})
        shader.bind()
        shader.uniform_float("color", (0.0, 1.0, 0.0, 0.7))
        batch.draw(shader)

        # bgl.glEnd()
        bgl.glLineWidth(1)
        bgl.glDisable(bgl.GL_BLEND)
        bgl.glDisable(bgl.GL_LINE_SMOOTH)
        bgl.glEnable(bgl.GL_DEPTH_TEST)
    
    def draw_callback_text_2D(self, operator, context):

        v3d = context.space_data
        rv3d = v3d.region_3d
        # region = v3d.region

        position_text = location_3d_to_region_2d(context.region, rv3d, context.object.location)

        font_id = 0
        blf.position(font_id, 2, 80, 0)
        blf.size(font_id, 20, 72)
        blf.color(font_id, 0.0, 1.0, 0.0, 1.0)

        #calculate the line size in mm
        length = ((context.object.matrix_world @ context.object.data.vertices[0].co - context.object.matrix_world @ context.object.data.vertices[1].co).length) * 1000
        

        blf.position(font_id, position_text[0], position_text[1], 0)
        blf.draw(font_id, '%.2f mm' % length)

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):

        args = (self, context)
        self._handle_3d = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, args, 'WINDOW', 'POST_VIEW')
        self.draw_event = context.window_manager.event_timer_add(0.1, window=context.window)

        #draw text 2D
        self._handle_text_2D = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_text_2D, args, 'WINDOW', 'POST_PIXEL')


        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        context.area.tag_redraw()

        if event.type in {'ESC'}:
            #remove timer handler
            context.window_manager.event_timer_remove(self.draw_event)
            #remove lines handler
            bpy.types.SpaceView3D.draw_handler_remove(self._handle_3d, 'WINDOW')
            #remove text handler
            bpy.types.SpaceView3D.draw_handler_remove(self._handle_text_2D, 'WINDOW')

            return {'CANCELLED'}

        return {'PASS_THROUGH'}


class OT_SizesDrawer(bpy.types.Operator):
        bl_idname = 'scene.sizes_drawer'
        bl_label = 'project info'
        bl_options = {'REGISTER'}
        
        def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
            
            
            obj = context.object
            points_selected = utils.get_selected_points(obj)
            
            max_idx = len(obj.data.splines[0].points) - 1
            pairs = utils.get_points_pairs(points_selected, max_idx)
            print(f'PAIRS ARE: {pairs}')
            #get data to draw sizes of
            #1. get pairs or structure
            # pairs = [[0,1,0],[4,7,0],[8,12,9]]
            
            
            
            # size_vector = get_vector_from_coordinates(points_selected[0].co, points_selected[1].co)   
            # print(size_vector)
            
            # length_v = size_vector.length
            
            # center = get_vector_center(size_vector)
            # print(center)
            
            # p_sel_new = points_selected[0].co.copy()
            # p_sel_new.resize(3)
            
            # #determine args to send to drawcall  
            args = (self, context, pairs, obj)
            
            # self._handle_ruler_3d = bpy.types.SpaceView3D.draw_handler_add(utils.draw_size_ruler_3D, args, 'WINDOW', 'POST_VIEW')
            self._handle_text_2d = bpy.types.SpaceView3D.draw_handler_add(utils.draw_text_callback_2D, args, 'WINDOW', 'POST_PIXEL')

            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        
        def modal(self, context: bpy.types.Context, event: bpy.types.Event):
            context.area.tag_redraw()
                        
            if event.type in {'ESC'}:
                bpy.types.SpaceView3D.draw_handler_remove(self._handle_text_2d, 'WINDOW')
                # bpy.types.SpaceView3D.draw_handler_remove(self._handle_ruler_3d, 'WINDOW')
                return {'CANCELLED'}
            
            return {'PASS_THROUGH'}
            
            
#---------------------------------------------------------------------------------------------------
# resgister / unregister
#---------------------------------------------------------------------------------------------------

classes = (
    CustomersBaseHandler,
    WallBuilder,
    OpeningsHandler,
    OpeningsAttacher,
    OpeningsAligner,
    BuildingAssembler, 
    SnappingCopyHandler,
    CurveAdder,
    BoundingsHaldler,
    ExtraCurvesEnabler,
    FBXLibraryImporter,
    OT_TestModalOperator,
    OT_TestGPUDrawer,
    OT_SizesDrawer
)

def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)


def unregister():
    from bpy.utils import unregister_class
    for cls in classes:
        unregister_class(cls)
