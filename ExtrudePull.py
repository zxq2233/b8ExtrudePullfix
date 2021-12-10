"""
	Copyright (C) 2018 Vladislav Kindushov, Blender 2.7x Version
		https://github.com/Darcvizer/Destructive-Extrude
		
	Copyright (C) 2019-2119 Martin Capitanio <capnm@capitanio.org>.
	All Rights Reserved.

	This program is free software: you can redistribute it and/or modify
	it under the terms of the GNU General Public License as published by
	the Free Software Foundation, either version 3 of the License, or
	(at your option) any later version.

	This program is distributed in the hope that it will be useful,
	but WITHOUT ANY WARRANTY; without even the implied warranty of
	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
	GNU General Public License for more details.

	You should have received a copy of the GNU General Public License
	along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import bpy
from bpy_extras import view3d_utils
from mathutils import Vector, kdtree
from mathutils.geometry import intersect_line_plane
from mathutils.bvhtree import BVHTree

import numpy as np

bl_info = {
	"name": "Extrude Pull",
	"location": "Edit Mode: Mesh > Extrude > Extrude Pull Geometry",
	"description": "Extrude unwanted geometry away",
	"author": "Vladislav Kindushov, Martin Capitanio",
	"version": (1, 0, 7),
	"blender": (2, 80, 0),
	"category": "Mesh",
}


def Snap(self, context, location, normal, index, object, matrix):
	# Find nearest element for snap.
	location = object.matrix_world @ location
	BestLocation, tresh4, tresh5 = self.KDTreeSnap.find(location)

	# Find nearest direction.
	tresh1, BestDirection, tresh2, tresh3 = self.BVHTree.find_nearest(BestLocation)
	BestVertex, tresh4, tresh5 = self.KDTree.find(BestLocation)

	ToVertex = BestLocation
	FromVertex = BestVertex
	dvec = ToVertex - BestDirection
	dnormal = np.dot(dvec, BestDirection)
	SnapPoint = FromVertex + Vector(dnormal * BestDirection)
	SnapDistance = (FromVertex - SnapPoint).length

	if self.NormalMove:
		return SnapDistance
	else:
		return SnapPoint


def RayCast(self, event, context):
	scene = context.scene
	region = context.region
	rv3d = context.region_data
	coord = event.mouse_region_x, event.mouse_region_y

	# Get the ray from the viewport and mouse.
	view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord).normalized()
	ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
	ray_target = ray_origin + (view_vector * 10000)

	matrix = self.MainObject.matrix_world
	matrix_inv = matrix.inverted()
	ray_origin_obj = matrix_inv @ ray_origin
	ray_target_obj = matrix_inv @ ray_target
	ray_direction_obj = ray_target_obj - ray_origin_obj
	ray_direction_obj.normalize()

	result, location, normal, index = self.MainObject.ray_cast(
		ray_origin_obj, ray_direction_obj
	)

	if result:
		value = Snap(self, context, location, normal, index, self.MainObject, matrix)
		if value is None:
			return GetMouseLocation(self, event, context) - self.StartMouseLocation
		else:
			return value
	else:
		return GetMouseLocation(self, event, context) - self.StartMouseLocation


def CreateBVHTree(self, context):
	bvh = BVHTree.FromObject(
		self.ExtrudeObject,
		context.evaluated_depsgraph_get(),
		deform=False,
		cage=False,
		epsilon=0.0
	)
	self.BVHTree = bvh
	size = len(self.ExtrudeObject.data.vertices)
	kd = kdtree.KDTree(size)

	for i in self.ExtrudeObject.data.vertices:
		kd.insert(self.ExtrudeObject.matrix_world @ i.co.copy(), i.index)

	kd.balance()
	self.KDTree = kd

	size = len(self.MainObject.data.vertices)
	size2 = len(self.MainObject.data.edges)
	size3 = len(self.MainObject.data.polygons)
	kd2 = kdtree.KDTree(size + size2 + size3)

	for i in self.MainObject.data.vertices:
		kd2.insert(self.MainObject.matrix_world @ i.co, i.index)

	for i in self.MainObject.data.edges:
		pos = (
			self.MainObject.data.vertices[i.vertices[0]].co +
			self.MainObject.data.vertices[i.vertices[1]].co
		) / 2
		kd2.insert(self.MainObject.matrix_world @ pos, i.index + size)

	for i in self.MainObject.data.polygons:
		kd2.insert(self.MainObject.matrix_world @ i.center, i.index + size + size2)

	kd2.balance()
	self.KDTreeSnap = kd2


def CursorPosition(self, context, is_Set=False):
	if is_Set and self.CursorLocation != 'NONE':
		context.scene.cursor.location = self.CursorLocation
		bpy.context.scene.tool_settings.transform_pivot_point = self.PivotPoint
	else:
		self.CursorLocation = context.scene.cursor.location
		self.PivotPoint = context.scene.tool_settings.transform_pivot_point


def CreateNewObject(self, context):
	# Duplicate the object.
	bpy.ops.mesh.duplicate_move()
	bpy.ops.mesh.separate(type='SELECTED')
	bpy.ops.object.mode_set(mode='OBJECT')
	self.ExtrudeObject = context.selected_objects[-1]

	# Clear modifiers.
	while len(self.ExtrudeObject.modifiers) != 0:
		self.ExtrudeObject.modifiers.remove(self.ExtrudeObject.modifiers[0])


def GetVisualSetings(self, context, isSet=False):
	if isSet:
		context.active_object.show_all_edges = self.ShowAllEdges
		context.active_object.show_wire = self.ShowAllEdges
	else:
		self.ShowAllEdges = context.active_object.show_all_edges
		self.ShowAllEdges = context.active_object.show_wire


def SetVisualSetings(self, context):
	self.MainObject.show_all_edges = True
	self.MainObject.show_wire = True

	self.ExtrudeObject.display_type = 'WIRE'


def GetVisualModifiers(self, context, isSet=False):
	if isSet:
		for i in self.MainObject.modifiers:
			if i.name in self.VisibilityModifiers:
				i.show_viewport = True
	else:
		for i in self.MainObject.modifiers:
			if i.show_viewport:
				self.VisibilityModifiers.append(i.name)
				i.show_viewport = False


def CreateModifier(self, context):
	# Set Boolean.
	context.view_layer.objects.active = self.MainObject
	self.bool = context.object.modifiers.new('DestructiveBoolean', 'BOOLEAN')
	bpy.context.object.modifiers["DestructiveBoolean"].operation = 'DIFFERENCE'
	bpy.context.object.modifiers["DestructiveBoolean"].object = self.ExtrudeObject
	bpy.context.object.modifiers["DestructiveBoolean"].show_viewport = True
	# Set Solidify.
	context.view_layer.objects.active = self.ExtrudeObject
	context.object.modifiers.new('DestructiveSolidify', 'SOLIDIFY')
	context.object.modifiers['DestructiveSolidify'].use_even_offset = True
	context.object.modifiers['DestructiveSolidify'].offset = -0.99959


def GetMouseLocation(self, event, context):
	region = bpy.context.region
	rv3d = bpy.context.region_data
	coord = event.mouse_region_x, event.mouse_region_y
	view_vector_mouse = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
	ray_origin_mouse = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
	V_a = ray_origin_mouse + view_vector_mouse
	V_b = rv3d.view_rotation @ Vector((0.0, 0.0, -1.0))
	pointLoc = intersect_line_plane(ray_origin_mouse, V_a, context.object.location, V_b)
	loc = (self.GeneralNormal @ pointLoc) * -1
	return loc


def SetSolidifyValue(self, context, value):
	self.ExtrudeObject.modifiers[-1].thickness = value


def CalculateNormal(self, context):
	for i in self.ExtrudeObject.data.polygons:
		self.GeneralNormal += i.normal.copy()


def TransformObject(self, context):
	selObj = context.selected_objects
	bpy.ops.object.select_all(action='DESELECT')
	self.ExtrudeObject.select_set(True)
	context.view_layer.objects.active = self.ExtrudeObject
	bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
	bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS')
	bpy.ops.view3d.snap_cursor_to_selected()

	bpy.context.scene.tool_settings.transform_pivot_point = 'CURSOR'
	self.ExtrudeObject.scale = Vector((1.001, 1.001, 1.001))

	for i in selObj:
		i.select_set(True)
	context.view_layer.objects.active = self.MainObject


def GetFaceNormal(self, context):
	for i in self.ExtrudeObject.data.polygons:
		self.FaceNormal.append(i.normal.copy())


def GetMainVertsIndex(self, context):
	for i in self.ExtrudeObject.data.vertices:
		self.MainVertsIndex.append(i.index)


def SetForAxis(self, context):
	GetMainVertsIndex(self, context)
	context.view_layer.objects.active = self.ExtrudeObject
	for i in range(0, len(self.MainVertsIndex) - 1):
		self.StartVertsPos.append(self.ExtrudeObject.data.vertices[i].co.copy())
	index = []
	for f in self.ExtrudeObject.data.polygons:
		normal = f.normal
		for v in f.vertices:
			if v not in index:
				self.ExtrudeObject.data.vertices[
					v
				].co = normal * 0.02 + self.ExtrudeObject.data.vertices[v].co.copy()
				index.append(v)

	self.ExtrudeObject.modifiers[0].thickness = 0.00
	self.ExtrudeObject.modifiers[0].offset = 0
	bpy.ops.object.modifier_apply(
		 modifier=self.ExtrudeObject.modifiers[0].name
	)
	for i in range(len(self.MainVertsIndex) - 1, len(self.ExtrudeObject.data.vertices)):
		self.StartVertsPos.append(self.ExtrudeObject.data.vertices[i].co.copy())
		context.view_layer.objects.active = self.MainObject


def ReturnStartPosition(self, context):
	for i in range(len(self.MainVertsIndex) - 1, len(self.ExtrudeObject.data.vertices)):
		self.ExtrudeObject.data.vertices[i].co = self.StartVertsPos[i]


def AxisMove(self, context, value):
	axis = Vector()
	if self.AxisMove == 'X':
		axis = Vector((-1.0, 0.0, 0.0))
	elif self.AxisMove == 'Y':
		axis = Vector((0.0, -1.0, 0.0))
	elif self.AxisMove == 'Z':
		axis = Vector((0.0, 0.0, -1.0))

	for i in range(len(self.MainVertsIndex), len(self.ExtrudeObject.data.vertices)):
		vertPos = ((axis * value) + self.StartVertsPos[i])
		self.ExtrudeObject.data.vertices[i].co = vertPos


def Cancel(self, context):
	bpy.data.objects.remove(self.ExtrudeObject)
	context.view_layer.objects.active = self.MainObject
	bpy.ops.object.modifier_remove(modifier='DestructiveBoolean')
	GetVisualSetings(self, context, True)
	GetVisualModifiers(self, context, True)
	bpy.ops.object.mode_set(mode='EDIT')


def Finish(self, context, BevelUpdate=False):
	rayCastFace = []
	if self.NormalMove:
		context.view_layer.objects.active = self.ExtrudeObject
		GetMainVertsIndex(self, context)
		bpy.ops.object.modifier_apply(
			modifier=self.ExtrudeObject.modifiers[0].name
		)
		bpy.ops.object.mode_set(mode='EDIT')
		bpy.ops.object.mode_set(mode='OBJECT')

	context.view_layer.objects.active = self.MainObject
	bpy.ops.object.modifier_apply(modifier='DestructiveBoolean')
	bpy.context.view_layer.update()
	context.active_object.data.update()
	context.active_object.data.update(calc_edges=False)
	context.active_object.update_tag(refresh={'OBJECT', 'DATA', 'TIME'})
	bpy.ops.object.mode_set(mode='EDIT')
	bpy.ops.object.mode_set(mode='OBJECT')

	for f in self.ExtrudeObject.data.polygons:
		faceCenter = self.ExtrudeObject.matrix_world @ f.center
		faceNormal = self.ExtrudeObject.matrix_world @ f.normal
		StartPoint = ((faceNormal * -1) * 0.003) + faceCenter

		center = self.MainObject.matrix_world.inverted() @ StartPoint
		normal = self.MainObject.matrix_world.inverted() @ faceNormal
		result, location, normal, index = self.MainObject.ray_cast(
			center, normal, distance=0.005
		)
		if result:
			rayCastFace.append(index)
			self.MainObject.data.polygons[index].select = True

	bpy.context.scene.tool_settings.transform_pivot_point = 'CURSOR'
	bpy.ops.transform.resize(value=(1 - 0.001, 1 - 0.001, 1 - 0.001))
	bpy.context.scene.tool_settings.transform_pivot_point = 'MEDIAN_POINT'

	for f in self.MainObject.data.polygons:
		f.select = False

	for f in self.ExtrudeObject.data.polygons:
		lose = False
		for v in f.vertices:
			if v in self.MainVertsIndex:
				lose = True
				break
		if lose:
			continue
		else:
			faceCenter = self.ExtrudeObject.matrix_world @ f.center
			faceNormal = self.ExtrudeObject.matrix_world @ f.normal
			StartPoint = ((faceNormal * -1) * 0.003) + faceCenter

			center = self.MainObject.matrix_world.inverted() @ StartPoint
			normal = self.MainObject.matrix_world.inverted() @ faceNormal
			result, location, normal, index = self.MainObject.ray_cast(
				center, normal, distance=0.005
			)
			if result:
				self.MainObject.data.polygons[index].select = True

	bpy.data.objects.remove(self.ExtrudeObject)
	GetVisualSetings(self, context, True)
	GetVisualModifiers(self, context, True)
	bpy.ops.object.mode_set(mode='EDIT')
	bpy.ops.mesh.remove_doubles(threshold=0.001, use_unselected=True)


class ExtrudePull(bpy.types.Operator):
	bl_idname = "mesh.extrude_pull"
	bl_label = "Extrude Pull Geometry"
	bl_options = {"REGISTER", "UNDO", "GRAB_CURSOR", "BLOCKING"}
	bl_description = "Extrude with a geometry removal"

	@classmethod
	def poll(cls, context):
		# Disable for Vertex and Edge select mode (add-on crash).
		if tuple(bpy.context.tool_settings.mesh_select_mode) == (False, False, True):
			if context.active_object.data.count_selected_items()[2] > 0:
				return (context.mode == "EDIT_MESH")
		return False

	def invoke(self, context, event):
		if context.space_data.type != 'VIEW_3D':
			self.report({'WARNING'}, "The operator is not called in 3D Viewport.")
			return {'CANCELLED'}

		self.KDTreeSnap = None
		self.KDTree = None
		self.BVHTree = None
		self.PivotPoint = None
		self.MainVertsIndex = []
		self.AxisMove = 'Z'
		self.StartVertsPos = []
		self.NormalMove = True
		self.GeneralNormal = Vector((0.0, 0.0, 0.0))
		self.FaceNormal = []
		self.ShowAllEdges = None
		self.ShowWire = None
		self.CursorLocation = None
		self.VisibilityModifiers = []
		self.MainObject = context.active_object
		self.ExtrudeObject = None
		self.SaveSelectFaceForCancel = None

		GetVisualModifiers(self, context)
		GetVisualSetings(self, context)
		CursorPosition(self, context)
		CreateNewObject(self, context)
		CreateBVHTree(self, context)
		CreateModifier(self, context)
		SetVisualSetings(self, context)
		TransformObject(self, context)
		CalculateNormal(self, context)
		self.StartMouseLocation = GetMouseLocation(self, event, context)
		# print('StartMouseLocation', self.StartMouseLocation)

		context.window_manager.modal_handler_add(self)
		return {'RUNNING_MODAL'}

	def modal(self, context, event):
		if event.type == 'MOUSEMOVE':
			value = GetMouseLocation(self, event, context) - self.StartMouseLocation
			if self.NormalMove:
				SetSolidifyValue(self, context, value)
			else:
				AxisMove(self, context, value)

		if event.ctrl:
			value = RayCast(self, event, context)
			if self.NormalMove:
				SetSolidifyValue(self, context, value)
			else:
				AxisMove(self, context, value)

		if event.type == 'X':
			if self.NormalMove:
				SetForAxis(self, context)
				self.NormalMove = False
			ReturnStartPosition(self, context)
			self.AxisMove = 'X'

		if event.type == 'Y':
			if self.NormalMove:
				SetForAxis(self, context)
				self.NormalMove = False
			ReturnStartPosition(self, context)
			self.AxisMove = 'Y'

		if event.type == 'Z':
			if self.NormalMove:
				SetForAxis(self, context)
				self.NormalMove = False
			ReturnStartPosition(self, context)
			self.AxisMove = 'Z'

		if event.type == 'LEFTMOUSE':
			Finish(self, context, BevelUpdate=False)
			return {'FINISHED'}

		if event.type in {'RIGHTMOUSE', 'ESC'}:
			Cancel(self, context)
			return {'CANCELLED'}
		return {'RUNNING_MODAL'}


addon_classes = (ExtrudePull, )

addon_classes_reg, addon_classes_unreg = bpy.utils.register_classes_factory(addon_classes)


def operator_draw(self, context):
	layout = self.layout
	col = layout.column(align=True)
	self.layout.operator_context = 'INVOKE_REGION_WIN'
	col.operator("mesh.extrude_pull", text="Extrude Pull Geometry")


def register():
	addon_classes_reg()
	bpy.types.VIEW3D_MT_edit_mesh_extrude.append(operator_draw)


def unregister():
	bpy.types.VIEW3D_MT_edit_mesh_extrude.remove(operator_draw)
	addon_classes_unreg()


if __name__ == "__main__":
	register()
