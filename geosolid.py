import argparse
import warnings

warnings.filterwarnings("ignore")

import os
import trimesh
import ezdxf
from ezdxf.gfxattribs import GfxAttribs
from shapely import MultiPolygon, Polygon
from shapely.ops import unary_union
import json

parser = argparse.ArgumentParser(description="geojson polygon layer to 3D model dxf converter tool")

# inputs
parser.add_argument('in_file', type=str, help="path to geojson polygon layer")
parser.add_argument("height_field", type=str, help="name of field containing heights of polygons")
parser.add_argument("-z", "--z_level_field", metavar='', type=str, default=None,
                    help="name of field containing z-levels of polygons", required=False)
parser.add_argument("-t", "--output_type", metavar='', type=str, default="mesh",
                    help="output cad object type: 'mesh' or 'solid', default is 'mesh': runs much faster",
                    required=False)
parser.add_argument("-b", "--buffer_tolerance", metavar='', type=float, default=0.1,
                    help="float number of buffer distance, default is 0.1", required=False)
parser.add_argument("-s", "--simplify_tolerance", metavar='', type=float, default=0.1,
                    help="float number of simplify ratio, default is 0.1", required=False)
parser.add_argument("-n", "--normalize", metavar='', type=lambda x: x.lower() == "true", default=True,
                    help="normalize polygons, default is True", required=False)
args = parser.parse_args()

# params
in_file = args.in_file
height_field = args.height_field
z_level_field = args.z_level_field
output_type = args.output_type
buffer_tolerance = args.buffer_tolerance
simplify_tolerance = args.simplify_tolerance
normalize = args.normalize

# outputs
file_folder = os.path.dirname(in_file)
out_file = os.path.join(file_folder, os.path.basename(in_file).replace('.geojson', '.dxf').replace('.json', '.dxf'))

# constants
DEFAULT_HEIGHT = 3.0  # default height for extruded meshes
SCALE_FACTOR = 1.0  # scale factor for normalizing polygons, default is 1.0
SHIFTS = [
    (0.0, 0.0, 0.0),
    (0.1, 0.0, 0.0),
    (-0.1, 0.1, 0.0),
    (-0.1, 0.0, 0.0),
    (0.1, -0.1, 0.0),
]  # distances to move meshes in order to combine them with existing ones
MAIN_LAYER = GfxAttribs(layer="all", color=252)  # main layer in output cad file
ERRORS_LAYER = GfxAttribs(layer="errors", color=80)  # errors layer for corrupted meshes


def extract_all_coords(geojson_data):
    # get all coordinates from a whole layer

    all_coords = []
    for feature in geojson_data:
        geom = feature["geometry"]
        if geom["type"] == "Polygon":
            for ring in geom["coordinates"]:
                all_coords.extend(ring)
        elif geom["type"] == "MultiPolygon":
            for polygon in geom["coordinates"]:
                for ring in polygon:
                    all_coords.extend(ring)

    return all_coords


def data_collection(file):
    # step 1, collect polygon parts as shapely polygons with height values from geojson

    dict_polygons = {}
    with open(file, 'r', encoding='utf-8') as geodata:
        data = json.load(geodata)

    all_coords = extract_all_coords(data['features'])
    min_x = min(point[0] for point in all_coords)
    min_y = min(point[1] for point in all_coords)
    min_corner = (min_x, min_y)

    for i_row, row in enumerate(data['features']):
        geom = row['geometry']
        coordinates = geom['coordinates']
        properties = row['properties']
        for i_part, part in enumerate(coordinates):
            coords_main = []
            coords_holes = []

            # check for lakes
            for i_ring, ring in enumerate(part):
                holes = []
                for coor in ring:
                    if not i_ring:
                        if normalize:
                            coords_main.append(
                                ((coor[0] - min_corner[0]) * SCALE_FACTOR, (coor[1] - min_corner[1]) * SCALE_FACTOR))
                        else:
                            coords_main.append((coor[0], coor[1]))
                    else:
                        if normalize:
                            holes.append(
                                ((coor[0] - min_corner[0]) * SCALE_FACTOR, (coor[1] - min_corner[1]) * SCALE_FACTOR))
                        else:
                            holes.append((coor[0], coor[1]))
                coords_holes.append(holes)

            # create main polygon (outline)
            p_main = Polygon(coords_main, holes=[])

            # add lakes if exist
            for index_hole, hole in enumerate(coords_holes):
                p_hole = Polygon(hole, holes=[])
                if p_hole.exterior.is_ccw:
                    coords_holes[index_hole] = hole[::-1]

            # fix polygon, switch to clockwise
            if not p_main.exterior.is_ccw:
                p = Polygon(coords_main[::-1], holes=coords_holes)
            else:
                p = Polygon(coords_main, holes=coords_holes)

            # get height from specified field, convert it to float if attribute is string
            # set default height if it is not specified or negative
            hgt = properties.get(height_field, DEFAULT_HEIGHT)
            if isinstance(hgt, str):
                hgt = float(hgt) if hgt else DEFAULT_HEIGHT

            if not hgt or hgt <= 0.0:
                hgt = DEFAULT_HEIGHT

            # get building zlevel
            hgt_zlev = 0
            if z_level_field:
                hgt_zlev = properties.get(z_level_field, 0)

            # creating dicts like {polygon: height_meters, zlevel}
            dict_polygons[p] = [hgt, hgt_zlev]
    return dict_polygons


def transform_to_mesh(polygon_data):
    # step 2, convert polygons to meshes

    list_of_meshes = []
    list_of_broken_meshes = []

    # all done in order to avoid thin lines and other trashy geometries
    # 2.1 combining all shapes into a single multipolygon
    merged = unary_union(list(polygon_data.keys()))

    # squared buffer of multipolygon
    buffer_plus = merged.buffer(buffer_tolerance, cap_style='square', join_style='mitre')

    # convert result above to multipolygon is it is singlepart
    if buffer_plus.geom_type == 'Polygon':
        buffer_plus = MultiPolygon([buffer_plus])

    # collect all parts of multipolygon
    list_buff_plus = []
    for buff in buffer_plus.geoms:
        list_buff_plus.append(buff)

    # squared negative buffer of all buffers made in 2.1 with optional edits
    plus_dissolve = unary_union(list_buff_plus)
    buffer_minus = plus_dissolve.buffer(buffer_tolerance * -1, cap_style='square', join_style='mitre')

    # convert result above to multipolygon is it is singlepart
    if buffer_minus.geom_type == 'Polygon':
        buffer_minus = MultiPolygon([buffer_minus])

    # step 3, looping single parts of multipolygon
    # looking for initial geometries which intersect buffer parts
    for single_part in list(buffer_minus.geoms):
        # get intersecting shapely polygons
        intersecting_list = [p for p in polygon_data.keys() if p.intersects(single_part)]
        pre_meshes_list = []
        # loop intersecting polygons
        for int_poly in intersecting_list:
            # get data like unique height, unique z_level
            hgt_extrusion = polygon_data[int_poly][0]
            hgt_z_level = polygon_data[int_poly][1]

            # making a mesh
            mesh_cutter_geom = generate_union_mesh(int_poly, hgt_extrusion, hgt_z_level)
            if mesh_cutter_geom:
                pre_meshes_list.append(mesh_cutter_geom)

        mesh = None
        if pre_meshes_list:
            # combining all meshes together
            for i, cutter_mesh in enumerate(pre_meshes_list):
                if i == 0:
                    mesh = cutter_mesh
                else:
                    mesh_is_fine = False

                    # shifting meshes in order to get an appropriate intersection which will not lead
                    # to mesh geometry errors
                    for shift in SHIFTS:
                        cutter_mesh.apply_translation(shift)
                        # cutter_mesh.apply_translation(tuple(map(lambda x: x * 2, shift)))
                        new_mesh = mesh.union(cutter_mesh)
                        if new_mesh.is_volume:
                            mesh = new_mesh
                            mesh_is_fine = True
                            break
                    if not mesh_is_fine:
                        list_of_broken_meshes.append([cutter_mesh, ERRORS_LAYER])
            list_of_meshes.append([mesh, MAIN_LAYER])

    return list_of_meshes, list_of_broken_meshes


def generate_union_mesh(polygon, height, z_level_value):
    # extrude and collect meshes for a group of polygons

    # making a small positive buffer
    int_poly_buffer = polygon.buffer(buffer_tolerance, cap_style='flat', join_style='bevel')

    # simplifying buffer to clean possible garbage
    simplified_cutter = int_poly_buffer.simplify(tolerance=simplify_tolerance)

    # check if polygon is object with lakes
    if simplified_cutter.boundary.geom_type == 'MultiLineString':
        coords_cutter_main = []
        coords_cutter_holes = []

        # loop all parts and collect lakes
        for index_line, line in enumerate(simplified_cutter.boundary.geoms):
            if index_line:
                line_hole = [list(f) for f in line.coords[:]]
                coords_cutter_holes.append(line_hole)
            else:
                coords_cutter_main = [list(f) for f in line.coords[:]]
        p_cutter = Polygon(coords_cutter_main, coords_cutter_holes)  # polygon which will be extruded
    else:
        p_cutter = Polygon(simplified_cutter.boundary.coords[:], [])  # polygon which will be extruded

    # mesh extrusion
    mesh_cutter = trimesh.creation.extrude_polygon(p_cutter, height)
    if z_level_value:
        mesh_cutter.apply_translation((0.0, 0.0, z_level_value))

    # return mesh if it is real
    if mesh_cutter:
        return mesh_cutter


def dxf_create(mesh_list, mesh_list_corrupted):
    # step 4, dxf creation
    doc = ezdxf.new("R2000")
    doc.layers.add(name="all")

    # create layer for corrupted geometries
    if mesh_list_corrupted:
        doc.layers.add(name="errors")

    msp = doc.modelspace()
    # loop mesh list and put them into cad model list
    for m_list in [mesh_list, mesh_list_corrupted]:
        for i, mesh_part in enumerate(m_list):
            mesh_part[0].fix_normals()
            mesh = msp.add_mesh(dxfattribs=mesh_part[1])
            mesh.dxf.subdivision_levels = 0
            with mesh.edit_data() as mesh_data:
                mesh_data.vertices = mesh_part[0].vertices.tolist()
                mesh_data.faces = mesh_part[0].faces.tolist()

            if output_type != 'mesh':
                m_obj = ezdxf.render.MeshTransformer.from_builder(mesh)
                m_obj.render_3dsolid(msp, dxfattribs=mesh_part[1])
                msp.delete_entity(mesh)

    doc.saveas(out_file)
    return out_file


def run():
    polygon_data = data_collection(in_file)
    meshes, meshes_corrupted = transform_to_mesh(polygon_data)
    output = dxf_create(meshes, meshes_corrupted)
    return output


result = run()
print(result)
