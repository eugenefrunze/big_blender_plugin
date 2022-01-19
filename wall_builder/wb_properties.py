import bpy
from .. import data_types
from .. import utils
from . import wb_operators

from bpy.props import PointerProperty, EnumProperty, FloatProperty, BoolProperty, \
    IntProperty, FloatVectorProperty, CollectionProperty, StringProperty


#props for the scene -------------------------------------------------------------------------------
class WBSceneProps(bpy.types.PropertyGroup):
    plans_collection: PointerProperty(
        type=bpy.types.Collection,
        name='wb objects',
        description='The collection off levels objects to align')

    alignment_object: PointerProperty(
        type=bpy.types.Object,
        name='Alignment point',
        description='The object on the pivot point of which the rest of the objects are aligned')

    # customers = CollectionProperty(type=CustomersProps)

#wall builder objects props ---------------------------------------------------------------------------------
class WBProps(bpy.types.PropertyGroup):

    is_converted: BoolProperty(
        name='Is converted',
        description='If object an Wall builder object'
    )

    customer: EnumProperty(
        name='client preset',
        items=utils.get_customers_info(),
        update=wb_operators.WallBuilder.set_customer_preset
    )

    object_type: EnumProperty(
        name='object type',
        items=data_types.get_objects_types(),
        default='WALL'
    )

    is_inner_wall: BoolProperty(
        name='is inner wall',
        update=wb_operators.WallBuilder.set_customer_preset,
        default=False
    )

    level: EnumProperty(
        name='object level',
        items=data_types.levels
    )
    
    position: EnumProperty(
        name='position',
        items=(
            ('INSIDE', 'Inside', ''),
            ('CENTER', 'Center', ''),
            ('OUTSIDE', 'Outside', '')
            ),
        default='INSIDE',
        update=wb_operators.WallBuilder.set_wall_position
        )

    thickness: FloatProperty(
            name='wall thickness',
            default=0,
            update=wb_operators.WallBuilder.set_wall_position
        )

    height: FloatProperty(
            name='height',
            default=0,
            update=wb_operators.WallBuilder.set_wall_position
        )

    wall_profile_curve: PointerProperty(
        type=bpy.types.Object,
        name='taper profile for the wall'
    )

    opening_elevation: FloatProperty(
            name='openings average elevation',
            default=0
            )

    elevation: FloatProperty(
            name='object global elevation',
            default=0
            )

    opening_type: EnumProperty(
            name='opening type',
            items=data_types.openings_types
        )

    opening_top_offset: FloatProperty(
            name='opening top offset',
            default=0
        )

    bounding_object: PointerProperty(
        name='bounding object',
        type=bpy.types.Object,
        description='bounding box object, used maily as bool cutter object for openings'
    )


def register():
    from bpy.utils import register_class
    register_class(WBProps)
    register_class(WBSceneProps)

    bpy.types.Object.wall_builder_props = bpy.props.PointerProperty(type=WBProps)

    bpy.types.Scene.wall_builder_scene_props = bpy.props.PointerProperty(type=WBSceneProps)
    

def unregister():
    from bpy.utils import unregister_class
    unregister_class(WBProps)
    unregister_class(WBSceneProps)


if __name__ == '__main__':
    register()