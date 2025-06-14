# geosolid
A tool for converting polygons from geojson layer to meshes (solids) in CAD drawing. 
Originally was made for fast transform of spatial data to 3D printing CAD document.

![Table loook](https://pereverzev.info/geosolid/pic.png)

# Quickstart guide.

## Overview
Geosolid is completely a python tool, which takes a geojson polygon layer with a field containing heights and transforms them into extruded meshes which are collected in DXF file.

## Requirements:
1. **geojson polygon (multipolygon) layer**:
   * Must use a projected coordinate system (e.g., UTM, EPSG:3857, or local CRS). Degrees (WGS84) are not supported
   * Must be topologically valid (no self-intersections or inverted rings)
   * Example files are provided in the /samples folder.

2. pre-installed python modules:
* **ezdxf** - creation of dxf (mine is 1.4.2)
* **trimesh** - generating extruded meshes and combining them (mine is 4.6.11)
* **shapely** - collecting and combining polygons into multipart (mine is 2.1.1)
* **manifold3d** - driver to create triangle-based meshes for trimesh lib (mine is 3.1.1)
* **scipy** - graph computations for trimesh lib (mine is 1.15.3)
* **numpy** - array computations for trimesh lib (mine is 2.0.2)

## Basic Usage
Run the tool from the command line:

```python geosolid.py sample_layer.geojson height_field```

* `sample_layer.geojson`: Path to your GeoJSON file
* `height_field`: Name of the attribute field containing extrusion heights (in meters or other non-degree units)

## Output
* A DXF file named `sample_layer.dxf` will be created in the same directory.
* ⚠️ Warning: Existing files with the same name will be overwritten.

You can also specify some additional parameters:
* `-z , --z_level_field` name of field containing z-levels of polygons, just add -z field_with_z_value to command
* `-t , --output_type` output cad object type: 'mesh' or 'solid', default is 'mesh': runs much faster and allows user to edit vertices/faces, while solid is ready to print object
* `-b , --buffer_tolerance` float number of buffer distance, default is 0.1. This value is used for making positive and negative buffers with a purpose to find clusters of polygons, which can be combined
* `-s , --simplify_tolerance` float number of simplify ratio, default is 0.1. This value is used for geometry simplification which would be significant in mesh creation and 3D printing
* `-n, --normalize` normalize polygons, default is True. Normalization is used for shifting polygons' extent to (0, 0). Due to some calculation features if tool use native coordinates of object, final mesh shapes can be corrupted. That is why normalization should be True in order to make tool universal for many coordinate reference systems. So switching this parameter to False will produce meshes in native coordinates but also generate some geometry errors.


# Sample Workflow
1. Prepare Data:
* Load your polygons in QGIS → Fix errors (e.g., `Vector Geometry > Fix Geometries`)
* Export fixed polygon  layer as GeoJSON in projected CRS (EPSG:3857, UTM or local CRS)
* Check for polygon height attributes, they should be integer or real numbers

2. Run GeoSolid:

```python geosolid.py my_layer.geojson height_field```

3. Open DXF:
* Import the output into CAD software (e.g., AutoCAD, Blender) for further editing or printing.
