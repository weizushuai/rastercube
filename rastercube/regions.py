"""
Contains utility classes to deal with well-known regions (e.g. MODIS tiles)
"""
import os
import rastercube.utils as utils
import numpy as np
import argparse
from osgeo import ogr, osr


class ParseRegionAction(argparse.Action):
    def __init__(self, option_strings, dest, nargs=None, **kwargs):
        if nargs is not None:
            raise ValueError('nargs not allowed')
        super(ParseRegionAction, self).__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        v = values.split(':')
        if len(v) != 2:
            raise ValueError('Expected region_file:region1,region2')
        region_fname, region_names = v
        region_names = region_names.split(',')

        region = Regions(region_fname)
        polygons = map(lambda n: region.polygon_for_region(n), region_names)
        setattr(namespace, self.dest, polygons)


def add_region_arg(parser):
    """
    Given an argparse ArgumentParser, add a new commandline argument that
    can be used to select a subset of regions
    """
    parser.add_argument(
        '--regions', type=str, required=False, default=None,
        action=ParseRegionAction,
        help='Specify a set of regions using\n' +
             '  <region_file.geojson>:region1,region2'
    )


class Regions(object):
    """
    A helper class to load polygons defining regions from geojson.
    Region files should be simple geojson files containing Polygon
    features. Each polygon should have a name attribute that will be
    used to look it up.
    """
    def __init__(self, fname):
        ds = ogr.Open(fname)
        assert ds is not None, "Couldn't open %s" % fname
        layer = ds.GetLayer()
        assert layer is not None

        WGS84_SR = osr.SpatialReference()
        WGS84_SR.ImportFromEPSG(4326)

        shape_sr = osr.SpatialReference()
        shape_sr.ImportFromWkt(layer.GetSpatialRef().ExportToWkt())

        transform = osr.CoordinateTransformation(shape_sr, WGS84_SR)

        # http://geoinformaticstutorial.blogspot.ch/2012/10/accessing-vertices-from-polygon-with.html
        polygons = {}
        for feature in layer:
            attr = feature.items()
            newattr = {}
            # some attributes contains unicode character. ASCIIfy everything
            # TODO: A bit brutal, but easy...
            for k, v in attr.items():
                newk = k.decode('ascii', errors='ignore')
                newattr[newk] = v
            attr = newattr

            geometry = feature.GetGeometryRef()
            assert geometry.GetGeometryName() == 'POLYGON'
            # A ring is a polygon in shapefiles
            ring = geometry.GetGeometryRef(0)
            assert ring.GetGeometryName() == 'LINEARRING'
            # The ring duplicates the last point, so for the polygon to be
            # closed, last point should equal first point
            npoints = ring.GetPointCount()
            points = [ring.GetPoint(i) for i in xrange(npoints)]
            points = [transform.TransformPoint(*p) for p in points]
            # third column is elevation - discard
            points = np.array(points)[:, :2]
            # swap (lng, lat) to (lat, lng)
            points = points[:, ::-1]
            assert np.allclose(points[-1], points[0])

            name = attr['name']
            polygons[name] = points

        self.polygons = polygons

    def regions_names(self):
        return self.polygons.keys()

    def polygon_for_region(self, name):
        assert name in self.polygons, "Unknown region %s" % name
        return self.polygons[name]


REGIONS_COLLECTIONS = {}


def register_regions_collection(geojson_fname):
    """
    Given a geojson filename, will register it as a new region
    """
    name, ext = os.path.splitext(os.path.basename(geojson_fname))
    assert ext == '.geojson'
    REGIONS_COLLECTIONS[name] = Regions(geojson_fname)

register_regions_collection(utils.asset_fname('assets/modis_tiles.geojson'))
register_regions_collection(utils.asset_fname('assets/continents.geojson'))


def polygon_for_region(regspec):
    """
    Given a region specification in the format <regcol.regname> like
        "test_zones_1.h10v09_1"
        "modis_tiles.h10v09"
    Returns the polygon for said region
    """
    colname, regname = regspec.split('.')
    if colname not in REGIONS_COLLECTIONS:
        raise ValueError('Unknown region collection %s' % colname)
    reg = REGIONS_COLLECTIONS[colname]
    return reg.polygon_for_region(regname)
