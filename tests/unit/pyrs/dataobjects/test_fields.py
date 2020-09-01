# Standard and third party libraries
from collections import namedtuple
from copy import deepcopy
import copy
import numpy as np
from numpy.testing import assert_allclose, assert_equal
import os
import pytest
import random
from uncertainties import unumpy

# PyRs libraries
from pyrs.core.peak_profile_utility import EFFECTIVE_PEAK_PARAMETERS, get_parameter_dtype
from pyrs.core.workspaces import HidraWorkspace
from pyrs.dataobjects.constants import DEFAULT_POINT_RESOLUTION
from pyrs.dataobjects.fields import (aggregate_scalar_field_samples, fuse_scalar_field_samples,
                                     ScalarFieldSample, _StrainField, StrainField, StrainFieldSingle,
                                     StressField, stack_scalar_field_samples)
from pyrs.dataobjects.sample_logs import PointList
from pyrs.peaks import PeakCollection, PeakCollectionLite  # type: ignore
from pyrs.peaks.peak_collection import to_microstrain
from tests.conftest import assert_allclose_with_sorting

to_megapascal = StressField.to_megapascal
SampleMock = namedtuple('SampleMock', 'name values errors x y z')

DIRECTIONS = ('11', '22', '33')  # directions for the StrainField


@pytest.fixture(scope='module')
def field_cube_regular():
    r"""
    A volume, surface, and linear scan in a cube of side 4, with a linear intensity function.
    The sample points represent a regular 3D lattice
    """
    def intensity(x, y, z):
        return x + y + z

    def assert_checks(field):
        all_finite = np.all(np.isfinite(field.values))
        assert all_finite, 'some values are not finite'
        assert np.allclose(field.values, [intensity(*r) for r in list(field.coordinates)])

    values_returned = {'assert checks': assert_checks, 'edge length': 4}
    coordinates = np.transpose(np.mgrid[0:3:4j, 0:3:4j, 0:3:4j], (1, 2, 3, 0)).reshape(-1, 3)  # shape = (64, 3)
    values = np.array([intensity(*xyz) for xyz in coordinates])
    errors = 0.1 * values
    vx, vy, vz = list(coordinates.T)
    values_returned['volume scan'] = ScalarFieldSample('stress', values, errors, vx, vy, vz)
    # Surface scan perpendicular to vz
    coordinates_surface = np.copy(coordinates)
    coordinates_surface[:, 2] = 0.0  # each coordinate is now repeated four times
    values = np.array([intensity(*xyz) for xyz in coordinates_surface])
    errors = 0.1 * values
    vx, vy, vz = list(coordinates_surface.T)
    values_returned['surface scan'] = ScalarFieldSample('stress', values, errors, vx, vy, vz)
    # Linear scan along vx
    coordinates_linear = np.copy(coordinates_surface)
    coordinates_linear[:, 1] = 0.0  # each coordinate is now repeated 16 times
    values = np.array([intensity(*xyz) for xyz in coordinates_linear])
    errors = 0.1 * values
    vx, vy, vz = list(coordinates_linear.T)
    values_returned['linear scan'] = ScalarFieldSample('stress', values, errors, vx, vy, vz)
    return values_returned


@pytest.fixture(scope='module')
def field_cube_with_vacancies():
    r"""
    A volume scan in a cube of side 6, with a linear intensity function.
    The cube contains 6^3 = 216 points, of which 4^3 = 64 are interior points. We randomly delete
    half the interior points. Thus, the extents of the cube are still 0 and 6.
    """
    def intensity(x, y, z):
        return x + y + z

    def assert_checks(field):
        all_finite = np.all(np.isfinite(field.values))
        assert all_finite, 'some values are not finite'
        assert np.allclose(field.values, [intensity(*r) for r in list(field.coordinates)])

    values_returned = {'assert checks': assert_checks, 'edge length': 6}
    indexes_interior = list(range(64))  # a counter for the sample points not in the surface of the cube
    random.shuffle(indexes_interior)  # we will randomly select half of these indexes as vacancies
    indexes_vacancy = indexes_interior[::2]  # flag every other interior point index as a vacancy
    index_interior = 0  # start the counter for the interior points
    coordinates = list()
    for vx in range(0, 6):
        vx_is_interior = 0 < vx < 5  # vx is not on the surface of the cube
        for vy in range(0, 6):
            vy_is_interior = 0 < vy < 5  # vx and vy are not on the surface of the cube
            for vz in range(0, 6):
                xyz = [vx, vy, vz]
                if vx_is_interior and vy_is_interior and 0 < vz < 5:
                    if index_interior not in indexes_vacancy:
                        coordinates.append(xyz)
                    index_interior += 1
                else:
                    coordinates.append(xyz)  # no vacancies on the surface of the cube
    coordinates = np.array(coordinates)  # shape = (216 - 32, 3)
    assert len(coordinates) == 6 ** 3 - 32
    vx, vy, vz = list(coordinates.transpose())
    values = np.array([intensity(*r) for r in coordinates])
    errors = 0.1 * values
    values_returned['volume scan'] = ScalarFieldSample('stress', values, errors, vx, vy, vz)
    return values_returned


@pytest.fixture(scope='module')
def field_surface_with_vacancies():
    r"""
    A surface scan in a square of side 10, with a linear intensity function.
    The cube contains 10^2 = 100 points, of which 8^2 = 64 are interior points. We randomly delete
    half the interior points. Thus, the extents of the square are still 0 and 10.
    """
    def intensity(x, y, z):
        return x + y + z

    def assert_checks(field):
        all_finite = np.all(np.isfinite(field.values))
        assert all_finite, 'some values are not finite'
        assert np.allclose(field.values, [intensity(*r) for r in list(field.coordinates)])

    values_returned = {'assert checks': assert_checks, 'edge length': 10}
    indexes_interior = list(range(64))  # a counter for the sample points not in the surface of the cube
    random.shuffle(indexes_interior)  # we will randomly select half of these indexes as vacancies
    indexes_vacancy = indexes_interior[::2]  # flag every other interior point index as a vacancy
    index_interior = 0  # start the counter for the interior points
    coordinates = list()
    for vx in range(0, 10):
        vx_is_interior = 0 < vx < 9  # vx is not on the perimeter of the square
        for vy in range(0, 10):
            vz = 0  # declare a surface scan perpendicular to the vz-axis
            xyz = [vx, vy, vz]
            if vx_is_interior and 0 < vy < 9:
                if index_interior not in indexes_vacancy:
                    coordinates.append(xyz)
                index_interior += 1
            else:
                coordinates.append(xyz)  # no vacancies on the perimeter of the square
    coordinates = np.array(coordinates)  # shape = (100 - 32, 3)
    assert len(coordinates) == 10 ** 2 - 32
    vx, vy, vz = list(coordinates.transpose())
    values = np.array([intensity(*r) for r in coordinates])
    errors = 0.1 * values
    values_returned['surface scan'] = ScalarFieldSample('stress', values, errors, vx, vy, vz)
    return values_returned


@pytest.fixture(scope='module')
def field_linear_with_vacancies():
    r"""
    A linear scan in a line of side 100, with a linear intensity function.
    The line contains 100 points, of which 98 interior points. We randomly delete
    10 interior points. Thus, the extents of the line are still 0 and 100.
    """
    def intensity(x, y, z):
        return x + y + z

    def assert_checks(field):
        all_finite = np.all(np.isfinite(field.values))
        assert all_finite, 'some values are not finite'
        assert np.allclose(field.values, [intensity(*r) for r in list(field.coordinates)])

    values_returned = {'assert checks': assert_checks, 'edge length': 10}
    indexes_interior = list(range(98))  # a counter for the sample points not in the edges of the line
    random.shuffle(indexes_interior)  # we will randomly select 10 of these indexes as vacancies
    indexes_vacancy = indexes_interior[0: 10]  # flag the first 10 indexes as vacancies
    index_interior = 0  # start the counter for the interior points
    coordinates = list()
    for vx in range(0, 100):
        vy, vz = 0, 0  # declare a linear scan along the vx-axis
        xyz = [vx, vy, vz]
        if 0 < vx < 99:  # vx is not on the edge of the linear scan
            if index_interior not in indexes_vacancy:
                coordinates.append(xyz)
            index_interior += 1
        else:
            coordinates.append(xyz)  # no vacancies on the perimeter of the square
    coordinates = np.array(coordinates)  # shape = (90, 3)
    assert len(coordinates) == 100 - 10
    vx, vy, vz = list(coordinates.transpose())
    values = np.array([intensity(*r) for r in coordinates])
    errors = 0.1 * values
    values_returned['linear scan'] = ScalarFieldSample('stress', values, errors, vx, vy, vz)
    return values_returned


class TestScalarFieldSample:

    sample1 = SampleMock('lattice',
                         [1.000, 1.010, 1.020, 1.030, 1.040, 1.050, 1.060, 1.070, 1.080, 1.090],  # values
                         [0.000, 0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.009],  # errors
                         [0.000, 1.000, 2.000, 3.000, 4.000, 5.000, 6.000, 7.000, 8.000, 9.000],  # x
                         [0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000],  # y
                         [0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000]  # z
                         )

    # The last three points of sample1 overlaps with the first three points of sample1
    sample2 = SampleMock('lattice',
                         [1.071, 1.081, 1.091, 1.10, 1.11, 1.12, 1.13, 1.14, 1.15, 1.16],  # values
                         [0.008, 0.008, 0.008, 0.00, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06],  # errors
                         [7.009, 8.001, 9.005, 10.00, 11.00, 12.00, 13.00, 14.00, 15.00, 16.00],  # x
                         [0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000],  # y
                         [0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000]  # z
                         )

    sample3 = SampleMock('strain',
                         [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],  # values
                         [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],  # errors
                         [0.0, 0.5, 0.0, 0.5, 0.0, 0.5, 0.0, 0.5],  # x
                         [1.0, 1.0, 1.5, 1.5, 1.0, 1.0, 1.5, 1.5],  # y
                         [2.0, 2.0, 2.0, 2.0, 2.5, 2.5, 2.5, 2.5],  # z
                         )

    sample4 = SampleMock('strain',
                         [float('nan'), 0.1, 0.2, float('nan'), float('nan'), 0.5, 0.6, float('nan')],  # values
                         [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],  # errors
                         [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],  # x
                         [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],  # y
                         [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],  # z
                         )

    # Points 2 and 3 overlap
    sample5 = SampleMock('lattice',
                         [float('nan'), 1.0, 1.0, 2.0, 3.0, float('nan'), 0.1, 1.1, 2.1, 3.1, 4.1],
                         [0.0, 0.10, 0.11, 0.2, 0.3, 0.4, 0.1, 0.1, 0.2, 0.3, 0.4],
                         [0.0, 1.000, 1.001, 2.0, 3.0, 4.0, 0.0, 1.0, 2.0, 3.0, 4.0],  # x
                         [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0],  # y
                         [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0],  # z
                         )

    def test_init(self):
        assert ScalarFieldSample(*TestScalarFieldSample.sample1)
        assert ScalarFieldSample(*TestScalarFieldSample.sample2)
        assert ScalarFieldSample(*TestScalarFieldSample.sample3)
        sample_bad = list(TestScalarFieldSample.sample1)
        sample_bad[1] = [1.000, 1.010, 1.020, 1.030, 1.040, 1.050, 1.060, 1.070, 1.080]  # one less value
        with pytest.raises(AssertionError):
            ScalarFieldSample(*sample_bad)

    def test_len(self):
        assert len(ScalarFieldSample(*TestScalarFieldSample.sample1)) == 10

    def test_values(self):
        field = ScalarFieldSample(*TestScalarFieldSample.sample1)
        np.testing.assert_equal(field.values, TestScalarFieldSample.sample1.values)

    def test_errors(self):
        field = ScalarFieldSample(*TestScalarFieldSample.sample1)
        np.testing.assert_equal(field.errors, TestScalarFieldSample.sample1.errors)

    def test_sample(self):
        field = ScalarFieldSample(*TestScalarFieldSample.sample1)
        # Test get
        assert_allclose(unumpy.nominal_values(field.sample), TestScalarFieldSample.sample1.values)
        assert_allclose(unumpy.std_devs(field.sample), TestScalarFieldSample.sample1.errors)
        # Test set
        field.sample *= 2
        assert_allclose(unumpy.nominal_values(field.sample), 2 * np.array(TestScalarFieldSample.sample1.values))
        assert_allclose(unumpy.std_devs(field.sample), 2 * np.array(TestScalarFieldSample.sample1.errors))

    def test_point_list(self):
        field = ScalarFieldSample(*TestScalarFieldSample.sample1)
        np.testing.assert_equal(field.point_list.vx, TestScalarFieldSample.sample1.x)

    def test_coordinates(self):
        sample = list(TestScalarFieldSample.sample1)
        field = ScalarFieldSample(*sample)
        np.testing.assert_equal(field.coordinates, np.array(sample[3:]).transpose())

    def test_x(self):
        field = ScalarFieldSample(*TestScalarFieldSample.sample1)
        np.testing.assert_equal(field.x, TestScalarFieldSample.sample1.x)

    def test_y(self):
        field = ScalarFieldSample(*TestScalarFieldSample.sample1)
        np.testing.assert_equal(field.y, TestScalarFieldSample.sample1.y)

    def test_z(self):
        field = ScalarFieldSample(*TestScalarFieldSample.sample1)
        np.testing.assert_equal(field.z, TestScalarFieldSample.sample1.z)

    def test_isfinite(self):
        field = ScalarFieldSample(*TestScalarFieldSample.sample4).isfinite
        for attribute in ('values', 'errors', 'x', 'y', 'z'):
            assert getattr(field, attribute) == pytest.approx([0.1, 0.2, 0.5, 0.6])

    def test_interpolated_sample_regular(self, field_cube_regular):
        r"""
        Test with an input regular grid. No interpolation should be necessary because
        the regular grid built using the extents of the field coincide with the input
        sample points
        """
        # A volumetric sample in a cube of side 4, with an linear intensity function
        field = field_cube_regular['volume scan']
        interpolated = field.interpolated_sample(method='linear', keep_nan=True, resolution=DEFAULT_POINT_RESOLUTION,
                                                 criterion='min_error')
        assert len(interpolated) == field_cube_regular['edge length'] ** 3  # sample list spans a cube
        assert interpolated.point_list.is_equal_within_resolution(field.point_list,
                                                                  resolution=DEFAULT_POINT_RESOLUTION)
        field_cube_regular['assert checks'](interpolated)
        # A surface scan
        field = field_cube_regular['surface scan']  # 64 points, each point repeated once
        interpolated = field.interpolated_sample(method='linear', keep_nan=True, resolution=DEFAULT_POINT_RESOLUTION,
                                                 criterion='min_error')
        assert len(interpolated) == field_cube_regular['edge length'] ** 2  # sample list spans a square
        # `field` has 64 points, each point repeated four times. `interpolated` has 16 points, each is unique
        assert interpolated.point_list.is_equal_within_resolution(field.point_list,
                                                                  resolution=DEFAULT_POINT_RESOLUTION)
        field_cube_regular['assert checks'](interpolated)
        # A linear scan
        field = field_cube_regular['linear scan']  # 64 points, each point is repeated 16 times
        interpolated = field.interpolated_sample(method='linear', keep_nan=True, resolution=DEFAULT_POINT_RESOLUTION,
                                                 criterion='min_error')
        assert len(interpolated) == field_cube_regular['edge length']  # sample list spans a line of sampled points
        # `field` has 64 points, each point repeated 16 times. `interpolated` has 4 points, each is unique
        assert interpolated.point_list.is_equal_within_resolution(field.point_list,
                                                                  resolution=DEFAULT_POINT_RESOLUTION)
        field_cube_regular['assert checks'](interpolated)

    def test_interpolated_sample_cube_vacancies(self, field_cube_with_vacancies):
        r"""
        Test with an input regular grid spanning a cube, where some interior points are missing.
        `field` has 32 vacancies, thus a total of 6^3 - 32 points. Interpolated, on the other hand, has no
        vacancies. The reason lies in how the extents are calculated. See the example below for a square of
        side four on the [vx, vy] surface (vz=0 here) with two internal vacancies:
         o o o o
         o x o o
         o o x o
         o o o o
        the list of vx, vy, and vz have missing coordinates [1, 1, 0] and [2, 2, 0]:
        vx = [0, 0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 3]  # 14 points, two (interior) points missing
        vy = [0, 1, 2, 3, 0, 2, 3, 0, 1, 3, 0, 1, 2, 3]  # 14 points, two (interior) points missing
        vz = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        When calculating the extents, we look separately to each list, and find out the number of unique coordinates
        unique vx = [0, 1, 2, 3]  # there are three instances of vx==1 (same for vx==2), so they are captured
        unique vy = [0, 1, 2, 3]  # same scenario than that of vx
        unique vz = [0]
        Extents for vx are:
             minimum = 0
             maximum = 3
             step =(maximum - minimum) / (unique_count -1) = (3 - 0) / (4 - 1) = 1
        When calculating the grid spanned by these extents, we have a grid from zero to 3 with four points,
        and same for vy and vz (let's generalize here of a cube, not a square). Thus, the interpolated grid
        has no vacancies.
        This situation will happen only when the number of vacancies is sufficiently small that all values
        of vx, vy, and vz are captured.
        """
        field = field_cube_with_vacancies['volume scan']
        interpolated = field.interpolated_sample(method='linear', keep_nan=True, resolution=DEFAULT_POINT_RESOLUTION,
                                                 criterion='min_error')
        assert len(interpolated) == 6 ** 3
        field_cube_with_vacancies['assert checks'](interpolated)

    def test_interpolated_sample_surface_vacancies(self, field_surface_with_vacancies):
        r"""
        Test with an input regular grid spanning a square, where some interior points are missing.
                Test with an input regular grid spanning a cube, where some interior points are missing.
        `field` has 32 vacancies, thus a total of 6^3 - 32 points. Interpolated, on the other hand, has no
        vacancies. The reason lies in how the extents are calculated. See the example below for a square of
        side four on the [vx, vy] surface (vz=0 here) with two internal vacancies:
         o o o o
         o x o o
         o o x o
         o o o o
        the list of vx, vy, and vz have missing coordinates [1, 1, 0] and [2, 2, 0]:
        vx = [0, 0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 3]  # 14 points, two (interior) points missing
        vy = [0, 1, 2, 3, 0, 2, 3, 0, 1, 3, 0, 1, 2, 3]  # 14 points, two (interior) points missing
        vz = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        When calculating the extents, we look separately to each list, and find out the number of unique coordinates
        unique vx = [0, 1, 2, 3]  # there are three instances of vx==1 (same for vx==2), so they are captured
        unique vy = [0, 1, 2, 3]  # same scenario than that of vx
        unique vz = [0]
        Extents for vx are:
             minimum = 0
             maximum = 3
             step =(maximum - minimum) / (unique_count -1) = (3 - 0) / (4 - 1) = 1
        When calculating the grid spanned by these extents, we have a grid from zero to 3 with four points,
        and same for vy. Thus, the interpolated grid has no vacancies.
        This situation will happen only when the number of vacancies is sufficiently small that all values
        of vx, and vy are captured.
        """
        field = field_surface_with_vacancies['surface scan']
        interpolated = field.interpolated_sample(method='linear', keep_nan=True, resolution=DEFAULT_POINT_RESOLUTION,
                                                 criterion='min_error')
        assert len(interpolated) == 10 ** 2
        field_surface_with_vacancies['assert checks'](interpolated)

    def test_interpolated_sample_linear_vacancies(self, field_linear_with_vacancies):
        r"""
        Test with an input regular grid spanning a square, where some interior points are missing.
        """
        field = field_linear_with_vacancies['linear scan']
        interpolated = field.interpolated_sample(method='linear', keep_nan=True, resolution=DEFAULT_POINT_RESOLUTION,
                                                 criterion='min_error')
        assert len(interpolated) == 90
        field_linear_with_vacancies['assert checks'](interpolated)

    def test_extract(self):
        field = ScalarFieldSample(*TestScalarFieldSample.sample1)
        target_indexes = range(0, 10, 2)
        selection = field.extract(target_indexes)
        assert selection.name == 'lattice'
        np.testing.assert_equal(selection.values, [1.000, 1.020, 1.040, 1.060, 1.080])
        np.testing.assert_equal(selection.errors, [0.000, 0.002, 0.004, 0.006, 0.008])
        np.testing.assert_equal(selection.x, [0.000, 2.000, 4.000, 6.000, 8.000])

    def test_aggregate(self):
        sample1 = ScalarFieldSample(*TestScalarFieldSample.sample1)
        sample2 = ScalarFieldSample(*TestScalarFieldSample.sample2)
        sample = sample1.aggregate(sample2)
        # index 9 of aggregate sample corresponds to the last point of sample1
        # index 10 of aggregate sample corresponds to the first point of sample2
        np.testing.assert_equal(sample.values[9: 11], [1.090, 1.071])
        np.testing.assert_equal(sample.errors[9: 11], [0.009, 0.008])
        np.testing.assert_equal(sample.x[9: 11], [9.000, 7.009])

    def test_intersection(self):
        sample1 = ScalarFieldSample(*TestScalarFieldSample.sample1)
        sample = sample1.intersection(ScalarFieldSample(*TestScalarFieldSample.sample2))
        assert len(sample) == 6  # three points from sample1 and three points from sample2
        assert sample.name == 'lattice'
        np.testing.assert_equal(sample.values, [1.070, 1.080, 1.090, 1.071, 1.081, 1.091])
        np.testing.assert_equal(sample.errors, [0.007, 0.008, 0.009, 0.008, 0.008, 0.008])
        np.testing.assert_equal(sample.x, [7.000, 8.000, 9.000, 7.009, 8.001, 9.005])

    def test_coalesce(self):
        sample1 = ScalarFieldSample(*TestScalarFieldSample.sample1)
        sample = sample1.aggregate(ScalarFieldSample(*TestScalarFieldSample.sample2))
        sample = sample.coalesce(criterion='min_error')
        assert len(sample) == 17  # discard the last point from sample1 and the first two points from sample2
        assert sample.name == 'lattice'
        # index 6 of aggregate sample corresponds to index 6 of sample1
        # index 11 of aggregate sample corresponds to index 3 of sample2
        np.testing.assert_equal(sample.values[6: 11], [1.060, 1.070, 1.080, 1.091, 1.10])
        np.testing.assert_equal(sample.errors[6: 11], [0.006, 0.007, 0.008, 0.008, 0.0])
        np.testing.assert_equal(sample.x[6: 11], [6.000, 7.000, 8.000, 9.005, 10.00])

    def test_fuse_with(self):
        sample1 = ScalarFieldSample(*TestScalarFieldSample.sample1)
        sample = sample1.fuse_with(ScalarFieldSample(*TestScalarFieldSample.sample2), criterion='min_error')
        assert len(sample) == 17  # discard the last point from sample1 and the first two points from sample2
        assert sample.name == 'lattice'
        # index 6 of aggregate sample corresponds to index 6 of sample1
        # index 11 of aggregate sample corresponds to index 3 of sample2
        np.testing.assert_equal(sample.values[6: 11], [1.060, 1.070, 1.080, 1.091, 1.10])
        np.testing.assert_equal(sample.errors[6: 11], [0.006, 0.007, 0.008, 0.008, 0.0])
        np.testing.assert_equal(sample.x[6: 11], [6.000, 7.000, 8.000, 9.005, 10.00])

    def test_add(self):
        sample1 = ScalarFieldSample(*TestScalarFieldSample.sample1)
        sample = sample1 + ScalarFieldSample(*TestScalarFieldSample.sample2)
        assert len(sample) == 17  # discard the last point from sample1 and the first two points from sample2
        assert sample.name == 'lattice'
        # index 6 of aggregate sample corresponds to index 6 of sample1
        # index 11 of aggregate sample corresponds to index 3 of sample2
        np.testing.assert_equal(sample.values[6: 11], [1.060, 1.070, 1.080, 1.091, 1.10])
        np.testing.assert_equal(sample.errors[6: 11], [0.006, 0.007, 0.008, 0.008, 0.0])
        np.testing.assert_equal(sample.x[6: 11], [6.000, 7.000, 8.000, 9.005, 10.00])

    def test_export(self):
        # Create a scalar field
        xyz = [list(range(0, 10)), list(range(10, 20)), list(range(20, 30))]
        xyz = np.vstack(np.meshgrid(*xyz)).reshape(3, -1)  # shape = (3, 1000)
        signal, errors = np.arange(0, 1000, 1, dtype=float), np.zeros(1000, dtype=float)
        sample = ScalarFieldSample('strain', signal, errors, *xyz)

        # Test export to MDHistoWorkspace
        workspace = sample.export(form='MDHistoWorkspace', name='strain1')
        assert workspace.name() == 'strain1'

        # Test export to CSV file
        with pytest.raises(NotImplementedError):
            sample.export(form='CSV', file='/tmp/csv.txt')

    def test_to_md(self):
        field = ScalarFieldSample(*TestScalarFieldSample.sample3)
        assert field
        histo = field.to_md_histo_workspace('sample3', interpolate=False)
        assert histo
        assert histo.id() == 'MDHistoWorkspace'

        for i, (min_value, max_value) in enumerate(((0.0, 0.5), (1.0, 1.5), (2.0, 2.5))):
            dimension = histo.getDimension(i)
            assert dimension.getUnits() == 'mm'
            # adding half a bin each direction since values from mdhisto are boundaries and constructor uses centers
            assert dimension.getMinimum() == pytest.approx(min_value - 0.25)
            assert dimension.getMaximum() == pytest.approx(max_value + 0.25)
            assert dimension.getNBins() == 2

        np.testing.assert_equal(histo.getSignalArray().ravel(), self.sample3.values, err_msg='Signal')
        np.testing.assert_equal(histo.getErrorSquaredArray().ravel(), np.square(self.sample3.errors), err_msg='Errors')

        # clean up
        histo.delete()

    def test_extend_to_point_list(self, strain_object_1, strain_object_2):
        r"""
        strain_object_1 is a StrainField object made up of two non-overlapping StrainFieldSingle objects.
        strain_object_2 a StrainField object made up of two overlapping StrainFieldSingle objects
        """
        nan = float('nan')
        #
        # Corner case: the extended point list is the same as the point list
        field = strain_object_1.field
        point_list_extended = deepcopy(field.point_list)
        field_extended = field.extend_to_point_list(point_list_extended)
        assert id(field_extended) == id(field)  # we didn't do a thing
        #
        # Exception: the extended point list does not contain the point list of the field
        field = strain_object_1.field
        point_list_extended = strain_object_1.strains[0].field.point_list  # just half of field.point_list
        with pytest.raises(ValueError) as exception_info:
            field.extend_to_point_list(point_list_extended)
        assert 'The point list is not contained in' in str(exception_info.value)
        #
        # Use strain_object_1
        point_list_extended = strain_object_1.point_list
        # Extend the field of the first single strain object
        field = strain_object_1.strains[0].field
        assert_allclose(field.values, to_microstrain([0.01, 0.02, 0.03, 0.04]), atol=1)
        field_extended = field.extend_to_point_list(point_list_extended)
        assert field_extended.point_list == point_list_extended
        assert_allclose(field_extended.values, to_microstrain([0.01, 0.02, 0.03, 0.04, nan, nan, nan, nan]), atol=1)
        # Extend the field of the second single strain object
        field = strain_object_1.strains[1].field
        assert_allclose(field.values, to_microstrain([0.05, 0.06, 0.07, 0.08]), atol=1)
        field_extended = field.extend_to_point_list(point_list_extended)
        assert field_extended.point_list == point_list_extended
        assert_allclose(field_extended.values, to_microstrain([nan, nan, nan, nan, 0.05, 0.06, 0.07, 0.08]), atol=1)
        #
        # Use strain_object_2
        point_list_extended = strain_object_2.point_list
        # Extend the field of the first single strain object
        field = strain_object_2.strains[0].field
        assert_allclose(field.values, to_microstrain([0.01, 0.02, 0.03, 0.04]), atol=1)
        field_extended = field.extend_to_point_list(point_list_extended)
        assert field_extended.point_list == point_list_extended
        assert_allclose(field_extended.values, to_microstrain([0.01, 0.02, 0.03, 0.04, nan, nan, nan, nan]), atol=1)
        # Extend the field of the second single strain object
        field = strain_object_2.strains[1].field
        assert_allclose(field.values, to_microstrain([0.045, 0.05, 0.06, 0.07, 0.08]), atol=1)
        field_extended = field.extend_to_point_list(point_list_extended)
        assert field_extended.point_list == point_list_extended
        assert_allclose(field_extended.values, to_microstrain([nan, nan, nan, 0.045, 0.05, 0.06, 0.07, 0.08]), atol=1)


@pytest.fixture(scope='module')
def strain_field_samples(test_data_dir):
    r"""
    A number of StrainField objects from mock and real data
    """
    sample_fields = {}
    #####
    # The first sample has 2 points in each direction
    #####
    subruns = np.arange(1, 9, dtype=int)

    # create the test peak collection - d-refernce is 1 to make checks easier
    # uncertainties are all zero
    peaks_array = np.zeros(subruns.size, dtype=get_parameter_dtype('gaussian', 'Linear'))
    peaks_array['PeakCentre'][:] = 180.  # position of two-theta in degrees
    peaks_error = np.zeros(subruns.size, dtype=get_parameter_dtype('gaussian', 'Linear'))
    peak_collection = PeakCollection('dummy', 'gaussian', 'linear', wavelength=2.,
                                     d_reference=1., d_reference_error=0.)
    peak_collection.set_peak_fitting_values(subruns, peaks_array, parameter_errors=peaks_error,
                                            fit_costs=np.zeros(subruns.size, dtype=float))

    # create the test workspace - only sample logs are needed
    workspace = HidraWorkspace()
    workspace.set_sub_runs(subruns)
    # arbitray points in space
    workspace.set_sample_log('vx', subruns, np.arange(1, 9, dtype=int))
    workspace.set_sample_log('vy', subruns, np.arange(11, 19, dtype=int))
    workspace.set_sample_log('vz', subruns, np.arange(21, 29, dtype=int))

    # call the function
    strain = StrainFieldSingle(hidraworkspace=workspace, peak_collection=peak_collection)

    # test the result
    assert strain
    assert not strain.filenames
    assert len(strain) == subruns.size
    assert strain.peak_collections == [peak_collection]
    np.testing.assert_almost_equal(strain.values, 0.)
    np.testing.assert_equal(strain.errors, np.zeros(subruns.size, dtype=float))
    sample_fields['strain with two points per direction'] = strain

    #####
    # Create StrainField samples from two files and different peak tags
    #####
    # TODO: substitute/fix HB2B_1628.h5 with other data, because reported vx, vy, and vz are all 'nan'
    # filename_tags_pairs = [('HB2B_1320.h5', ('', 'peak0')), ('HB2B_1628.h5', ('peak0', 'peak1', 'peak2'))]
    filename_tags_pairs = [('HB2B_1320.h5', ('', 'peak0'))]
    for filename, tags in filename_tags_pairs:
        file_path = os.path.join(test_data_dir, filename)
        prefix = filename.split('.')[0] + '_'
        for tag in tags:
            sample_fields[prefix + tag] = StrainFieldSingle(filename=file_path, peak_tag=tag)
            assert sample_fields[prefix + tag].filenames == [filename]

    return sample_fields


class TestStrainFieldSingle:

    def test_overlapping_list(self):
        x = [0.0, 0.5, 0.0, 0.5, 0.0, 0.5, 0.0, 0.0]  # x
        y = [1.0, 1.0, 1.5, 1.5, 1.0, 1.0, 1.5, 1.5]  # y
        z = [2.0, 2.0, 2.0, 2.0, 2.5, 2.5, 2.5, 2.5]  # z
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]  # values
        errors = [1.0, 2.0, 1.0, 2.0, 1.0, 2.0, 1.0, 2.0]  # errors
        peak_collection = PeakCollectionLite('strain', strain=values, strain_error=errors)
        with pytest.raises(RuntimeError) as exception_info:
            StrainField(peak_collection=peak_collection, point_list=PointList([x, y, z]))
        assert 'sample points are overlapping' in str(exception_info.value)

    def test_d_reference(self):
        x = np.array([0.0, 0.5, 0.0, 0.5, 0.0, 0.5, 0.0, 0.5])
        y = np.array([1.0, 1.0, 1.5, 1.5, 1.0, 1.0, 1.5, 1.5])
        z = np.array([2.0, 2.0, 2.0, 2.0, 2.5, 2.5, 2.5, 2.5])
        point_list = PointList([x, y, z])
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
        errors = np.full(len(values), 1., dtype=float)
        strain = StrainField(peak_collection=PeakCollectionLite('strain',
                                                                strain=values, strain_error=errors),
                             point_list=point_list)

        D_REFERENCE = np.pi
        D_REFERENCE_ERROR = 42
        strain.set_d_reference((D_REFERENCE, D_REFERENCE_ERROR))

        d_reference = strain.get_d_reference()
        assert d_reference.point_list == point_list
        np.testing.assert_equal(d_reference.values, D_REFERENCE)
        np.testing.assert_equal(d_reference.errors, D_REFERENCE_ERROR)

    def test_set_d_reference(self, strain_single_object_0):
        r"""Test using a ScalarFieldSample"""
        d_spacing = strain_single_object_0.get_dspacing_center()
        expected = [1.00, 1.01, 1.02, 1.03, 1.04, 1.05, 1.06, 1.07]
        assert_allclose(d_spacing.values, expected, atol=0.001)
        # Set the reference spacings as the observed lattice plane spacings
        strain_single_object_0.set_d_reference(d_spacing)
        assert_allclose(strain_single_object_0.get_d_reference().values, expected)
        # There should be no strain, since the observed lattice plane spacings are the reference spacings
        assert_allclose(strain_single_object_0.values, np.zeros(8), atol=1.e-5)

    def test_get_peak_params(self, strain_field_samples):
        strain = strain_field_samples['strain with two points per direction']  # mock object

        # test that getting non-existant parameter works
        with pytest.raises(ValueError) as exception_info:
            strain.get_effective_peak_parameter('impossible')
        assert 'impossible' in str(exception_info.value)

        num_values = len(strain)
        for name in EFFECTIVE_PEAK_PARAMETERS:
            scalar_field = strain.get_effective_peak_parameter(name)
            assert scalar_field, f'Failed to get {name}'
            assert len(scalar_field) == num_values, f'{name} does not have correct length'


class Test_StrainField:

    class StrainFieldMock(StrainField):
        r"""Mocks a StrainField object overloading the initialization"""

        def __init__(self, *strains):
            for s in strains:
                assert isinstance(s, StrainFieldSingle)
            self._strains = strains

    def test_eq(self, strain_field_samples):
        strains_single_scan = copy.deepcopy(list(strain_field_samples.values()))
        # single-scan strains
        assert strains_single_scan[0] == strains_single_scan[0]
        assert (strains_single_scan[0] == strains_single_scan[1]) is False

        # multi-scan scans
        strain_multi = self.StrainFieldMock(*strains_single_scan)
        assert strain_multi == strain_multi
        assert (strain_multi == strains_single_scan[0]) is False
        strain_multi_2 = self.StrainFieldMock(*strains_single_scan[:-1])  # all except the last one
        assert (strain_multi == strain_multi_2) is False

    def test_stack_with(self, strain_stress_object_0, strain_stress_object_1):
        r"""
        Stack pair of strains.

        Description of strain_stress_object_0['strains']:
          RUN          vx-coordinate
        NUMBER  0.0  1.0  2.0  3.0  4.0  5.0
        1234    ****************************
        1235    ****************************
        1236    ****************************

        For simplicity, vy and vz values are all zero, so these are unidimensional scans

        From these four strains, we create strains in three dimensions:
            strain11 = strain_1234
            strain22 = strain_1235
            strain33 = strain_1237

        Description of strain_stress_object_1['strains']:
        We create four single strain instances, below is how they overlap over the vx's extent

              RUN          vx-coordinate
            NUMBER  0.0  1.0  2.0  3.0  4.0  5.0  6.0  7.0  8.0  9.0
            1234    **************************************
            1235         ******************
            1236                        ***********************
            1237              **************************************

        Runs 1235 and 1236 overlap in one point. 1235 is the run will the smallest error in strain.

        For simplicity, vy and vz values are all zero, so these are unidimensional scans

        From these four strains, we create strains in three dimensions:
            strain11 = strain_1234
            strain22 = strain_1235 + strain_1236
            strain33 = strain_1237
        """
        strains = strain_stress_object_0['strains']

        def assert_stacking(direction_left, direction_right):
            r"""Stack strains along two directions"""
            left, right = strains[direction_left].stack_with(strains[direction_right])
            # evaluate the stacked left direction
            assert_allclose(left.point_list.vx, [0., 1., 2., 3., 4.])
            assert left._strains == strains[direction_left]._strains
            assert_equal(left._winners.scan_indexes, [0, 0, 0, 0, 0])
            assert_equal(left._winners.point_indexes, [0, 1, 2, 3, 4])
            # evaluate the stacked right direction
            assert_allclose(right.point_list.vx, [0., 1., 2., 3., 4.])
            assert right._strains == strains[direction_right]._strains
            assert_equal(right._winners.scan_indexes, [0, 0, 0, 0, 0])
            assert_equal(right._winners.point_indexes, [0, 1, 2, 3, 4])

        assert_stacking('11', '22')
        assert_stacking('11', '33')
        assert_stacking('22', '33')

        strains = strain_stress_object_1['strains']
        #
        # Stack 11 and 22 directions
        left, right = strains['11'].stack_with(strains['22'])
        # evaluate the stacked 11 direction
        assert_allclose(left.point_list.vx, [0., 1., 2., 3., 4., 5., 6., 7., 8.0])
        assert left._strains == strains['11']._strains
        assert_equal(left._winners.scan_indexes, [0, 0, 0, 0, 0, 0, 0, 0, -1])
        assert_equal(left._winners.point_indexes, [0, 1, 2, 3, 4, 5, 6, 7, -1])
        # evaluate the stacked 22 direction
        assert_allclose(right.point_list.vx, [0., 1., 2., 3., 4., 5., 6., 7., 8.0])
        assert right._strains == strains['22']._strains
        assert_equal(right._winners.scan_indexes, [-1, 0, 0, 0, 0, 1, 1, 1, 1])
        assert_equal(right._winners.point_indexes, [-1, 0, 1, 2, 3, 1, 2, 3, 4])
        #
        # Stack 11 and 33 directions
        left, right = strains['11'].stack_with(strains['33'])
        # evaluate the stacked 11 direction
        assert_allclose(left.point_list.vx, [0., 1., 2., 3., 4., 5., 6., 7., 8.0, 9.0])
        assert left._strains == strains['11']._strains
        assert_equal(left._winners.scan_indexes, [0, 0, 0, 0, 0, 0, 0, 0, -1, -1])
        assert_equal(left._winners.point_indexes, [0, 1, 2, 3, 4, 5, 6, 7, -1, -1])
        # evaluate the stacked 33 direction
        assert_allclose(right.point_list.vx, [0., 1., 2., 3., 4., 5., 6., 7., 8.0, 9.0])
        assert right._strains == strains['33']._strains
        assert_equal(right._winners.scan_indexes, [-1, -1, 0, 0, 0, 0, 0, 0, 0, 0])
        assert_equal(right._winners.point_indexes, [-1, -1, 0, 1, 2, 3, 4, 5, 6, 7])
        #
        # Stack 22 and 33 directions
        left, right = strains['22'].stack_with(strains['33'])
        # evaluate the stacked 22 direction
        assert_allclose(left.point_list.vx, [1., 2., 3., 4., 5., 6., 7., 8.0, 9.0])
        assert left._strains == strains['22']._strains
        assert_equal(left._winners.scan_indexes, [0, 0, 0, 0, 1, 1, 1, 1, -1])
        assert_equal(left._winners.point_indexes, [0, 1, 2, 3, 1, 2, 3, 4, -1])
        # evaluate the stacked 33 direction
        assert_allclose(right.point_list.vx, [1., 2., 3., 4., 5., 6., 7., 8.0, 9.0])
        assert right._strains == strains['33']._strains
        assert_equal(right._winners.scan_indexes, [-1, 0, 0, 0, 0, 0, 0, 0, 0])
        assert_equal(right._winners.point_indexes, [-1, 0, 1, 2, 3, 4, 5, 6, 7])

    def test_mul(self, strain_object_0, strain_object_2):
        r"""
        Strain_object_0 is a StrainField object made up of one StrainFieldSingle object
            vx: [0., 1., 2., 3., 4., 5., 6., 7.]
        strain_object_2 is a StrainField object made up of two overlapping StrainFieldSingle objects
            vx: [1., 2., 3., 4.]  (vx of first StrainFieldSingle)
            vx:             [4., 5., 6., 7., 8.] (vy of first StrainFieldSingle)
            The first StrainFieldSingle has smaller errors in the strain
        """
        left, right = strain_object_0 * strain_object_2
        # evaluate the stacked first direction
        assert_allclose(left.point_list.vx, [0., 1., 2., 3., 4., 5., 6., 7., 8.0])
        assert left._strains == strain_object_0._strains
        assert_equal(left._winners.scan_indexes, [0, 0, 0, 0, 0, 0, 0, 0, -1])
        assert_equal(left._winners.point_indexes, [0, 1, 2, 3, 4, 5, 6, 7, -1])
        # evaluate the stacked second direction
        assert_allclose(right.point_list.vx, [0., 1., 2., 3., 4., 5., 6., 7., 8.0])
        assert right._strains == strain_object_2._strains
        assert_equal(right._winners.scan_indexes, [-1, 0, 0, 0, 0, 1, 1, 1, 1])
        assert_equal(right._winners.point_indexes, [-1, 0, 1, 2, 3, 1, 2, 3, 4])

    def test_rmul(self, strain_stress_object_1):
        strains = strain_stress_object_1['strains']
        strains12 = strains['11'] * strains['22']
        # Here comes the call to rmul by stacking a list of two strains against a third strain
        strains1, strains2, strains3 = strains12 * strains['33']
        # Compare against stacking the three strains at the same time
        strains123 = _StrainField.stack_strains(*strains.values())
        assert_allclose(strains1.values, strains123[0].values)
        assert_allclose(strains2.values, strains123[1].values)
        assert_allclose(strains3.values, strains123[2].values)


class TestStrainField:

    def test_peak_collection(self, strain_field_samples):
        strain = strain_field_samples['strain with two points per direction']
        assert isinstance(strain.peak_collections, list)
        assert len(strain.peak_collections) == 1
        assert isinstance(strain.peak_collections[0], PeakCollection)
        # TODO: test the RuntimeError when the strain is a composite

    def test_peak_collections(self, strain_field_samples):
        strain = strain_field_samples['strain with two points per direction']
        assert len(strain.peak_collections) == 1
        assert isinstance(strain.peak_collections[0], PeakCollection)

    def test_coordinates(self, strain_field_samples):
        strain = strain_field_samples['strain with two points per direction']
        coordinates = np.array([[1., 11., 21.], [2., 12., 22.], [3., 13., 23.], [4., 14., 24.],
                                [5., 15., 25.], [6., 16., 26.], [7., 17., 27.], [8., 18., 28.]])
        assert np.allclose(strain.coordinates, coordinates)

    def test_fuse_with(self, strain_field_samples):
        strain1 = strain_field_samples['HB2B_1320_peak0']
        strain2 = strain_field_samples['strain with two points per direction']
        strain = strain1.fuse_with(strain2)
        assert strain.peak_collections == [strain1.peak_collections[0], strain2.peak_collections[0]]
        assert np.allclose(strain.coordinates, np.concatenate((strain1.coordinates, strain2.coordinates)))
        assert strain.field  # should return something

        # fusing a scan with itself creates a new copy of the strain
        assert strain.peak_collections[0] == strain1.peak_collections[0]

    def test_add(self, strain_field_samples):
        strain1 = strain_field_samples['HB2B_1320_peak0']
        strain2 = strain_field_samples['strain with two points per direction']
        strain = strain1 + strain2
        assert strain.peak_collections == [strain1.peak_collections[0], strain2.peak_collections[0]]
        assert np.allclose(strain.coordinates, np.concatenate((strain1.coordinates, strain2.coordinates)))

    def test_create_strain_field_from_scalar_field_sample(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]  # values
        errors = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]  # errors
        x = [0.0, 0.5, 0.0, 0.5, 0.0, 0.5, 0.0, 0.5]  # x
        y = [1.0, 1.0, 1.5, 1.5, 1.0, 1.0, 1.5, 1.5]  # y
        z = [2.0, 2.0, 2.0, 2.0, 2.5, 2.5, 2.5, 2.5]  # z
        strain = StrainField(peak_collection=PeakCollectionLite('strain', strain=values, strain_error=errors),
                             point_list=PointList([x, y, z]))
        assert np.allclose(strain.values, to_microstrain(values), atol=1)
        assert np.allclose(strain.x, x)

    def test_small_fuse(self):
        '''This test does a fuse with shared PointList that choses every other
        point from each contributing StrainField'''
        x = [0.0, 0.5, 0.0, 0.5, 0.0, 0.5, 0.0, 0.5]  # x
        y = [1.0, 1.0, 1.5, 1.5, 1.0, 1.0, 1.5, 1.5]  # y
        z = [2.0, 2.0, 2.0, 2.0, 2.5, 2.5, 2.5, 2.5]  # z
        point_list = PointList([x, y, z])

        values1 = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]  # values
        errors1 = [1.0, 2.0, 1.0, 2.0, 1.0, 2.0, 1.0, 2.0]  # errors
        strain1 = StrainField(peak_collection=PeakCollectionLite('strain',
                                                                 strain=values1, strain_error=errors1),
                              point_list=point_list)
        assert np.allclose(strain1.values, to_microstrain(values1))
        assert np.allclose(strain1.x, x)

        values2 = [9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0]  # values
        errors2 = [2.0, 1.0, 2.0, 1.0, 2.0, 1.0, 2.0, 1.0]  # errors
        strain2 = StrainField(peak_collection=PeakCollectionLite('strain',
                                                                 strain=values2, strain_error=errors2),
                              point_list=point_list)
        assert np.allclose(strain2.values, to_microstrain(values2))
        assert np.allclose(strain2.x, x)

        strain_fused = strain1.fuse_with(strain2)

        # confirm that the points were unchanged
        assert len(strain_fused) == len(strain1)
        assert strain_fused.point_list == point_list

        field = strain_fused.field
        # all uncertainties should be identical
        np.testing.assert_equal(field.errors, to_microstrain(np.ones(len(field))))
        # every other point comes from a single field
        np.testing.assert_equal(field.values, to_microstrain([1., 10., 3., 12., 5., 14., 7., 16.]))

    def test_small_stack(self):
        x = [0.0, 0.5, 0.0, 0.5, 0.0, 0.5, 0.0, 0.5]  # x
        y = [1.0, 1.0, 1.5, 1.5, 1.0, 1.0, 1.5, 1.5]  # y
        z = [2.0, 2.0, 2.0, 2.0, 2.5, 2.5, 2.5, 2.5]  # z
        point_list1 = PointList([x, y, z])

        # changes a single x-value in the last 4 points
        x = [0.0, 0.5, 0.0, 0.5, 1.0, 1.5, 1.0, 1.5]  # x
        y = [1.0, 1.0, 1.5, 1.5, 1.0, 1.0, 1.5, 1.5]  # y
        z = [2.0, 2.0, 2.0, 2.0, 2.5, 2.5, 2.5, 2.5]  # z
        point_list2 = PointList([x, y, z])

        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]  # values
        errors = np.full(len(values), 1., dtype=float)

        strain1 = StrainField(peak_collection=PeakCollectionLite('strain',
                                                                 strain=values, strain_error=errors),
                              point_list=point_list1)

        strain2 = StrainField(peak_collection=PeakCollectionLite('strain',
                                                                 strain=values, strain_error=errors),
                              point_list=point_list2)

        # simple case of all points are identical - union
        strain_stack = strain1.stack_with(strain1, mode='union')
        assert len(strain_stack) == 2
        for stacked, orig in zip(strain_stack, [strain1, strain1]):
            assert len(stacked) == len(orig)
            assert stacked.point_list == orig.point_list
            np.testing.assert_equal(stacked.values, orig.values)

        # case when there are 4 points not commont
        strain_stack = strain1.stack_with(strain2, mode='union')
        assert len(strain_stack) == 2
        assert len(strain_stack[0]) == len(strain_stack[1])
        for stacked, orig in zip(strain_stack, [strain1, strain2]):
            assert stacked.peak_collections[0] == orig.peak_collections[0]
            assert stacked.point_list != orig.point_list
            assert len(stacked.point_list) == 12
            field = stacked.field
            assert field
            assert len(field) == 12
            # TODO should confirm 4 nans in each
            assert len(stacked.point_list) == 12  # 4 points in common

        # simple case of all points are identical - intersection
        ''' THIS ISN'T CURRENTLY SUPPORTED
        strain_stack = strain1.stack_with(strain1, mode='intersection')
        assert len(strain_stack) == 2
        for stacked, orig in zip(strain_stack, [strain1, strain1]):
            assert len(stacked) == len(orig)
            assert stacked.point_list == orig.point_list
        '''

    def test_create_strain_field_from_file_no_peaks(self, test_data_dir):
        # this project file doesn't have peaks in it
        file_path = os.path.join(test_data_dir, 'HB2B_1060_first3_subruns.h5')
        try:
            _ = StrainField(file_path)  # noqa F841
            assert False, 'Should not be able to read ' + file_path
        except IOError:
            pass  # this is what should happen

    def test_from_file(self, test_data_dir):
        file_path = os.path.join(test_data_dir, 'HB2B_1320.h5')
        strain = StrainField(filename=file_path, peak_tag='peak0')

        assert strain
        assert strain.field
        assert strain.get_effective_peak_parameter('Center')

    def test_fuse_strains(self, strain_field_samples):
        # TODO HB2B_1320_peak0 and HB2B_1320_ are the same scan. We need two different scans
        strain1 = strain_field_samples['HB2B_1320_peak0']
        strain2 = strain_field_samples['HB2B_1320_']
        strain3 = strain_field_samples['strain with two points per direction']
        # Use fuse_strains().
        strain_fused = StrainField.fuse_strains(strain1, strain2, strain3, resolution=DEFAULT_POINT_RESOLUTION,
                                                criterion='min_error')
        # the sum should give the same, since we passed default resolution and criterion options
        strain_sum = strain1 + strain2 + strain3
        for strain in (strain_fused, strain_sum):
            assert len(strain) == 312 + 8  # strain1 and strain2 give strain1 because they contain the same data
            assert strain.peak_collections == [s.peak_collections[0] for s in (strain1, strain2, strain3)]
            values = np.concatenate((strain1.values, strain3.values))  # no strain2 because it's the same as strain1
            assert_allclose_with_sorting(strain.values, values)

    def test_d_reference(self):
        # create two strains
        x = np.array([0.0, 0.5, 0.0, 0.5])
        y = np.array([1.0, 1.0, 1.5, 1.5])
        z = np.array([2.0, 2.0, 2.0, 2.0])
        point_list = PointList([x, y, z])
        values = np.array([1.0, 2.0, 3.0, 4.0])
        errors = np.full(len(values), 1., dtype=float)
        strain1 = StrainField(peak_collection=PeakCollectionLite('strain',
                                                                 strain=values, strain_error=errors),
                              point_list=point_list)

        x = np.array([0.0, 0.5, 0.0, 0.5])
        y = np.array([1.0, 1.0, 1.5, 1.5])
        z = np.array([2.5, 2.5, 2.5, 2.5])
        point_list = PointList([x, y, z])
        values = np.array([5.0, 6.0, 7.0, 8.0])
        errors = np.full(len(values), 1., dtype=float)
        strain2 = StrainField(peak_collection=PeakCollectionLite('strain',
                                                                 strain=values, strain_error=errors),
                              point_list=point_list)

        # fuse them together to get a StrainField with multiple peakcollections
        strain = strain1.fuse_with(strain2)
        del strain1
        del strain2

        D_REFERENCE = np.pi
        D_REFERENCE_ERROR = 42
        strain.set_d_reference((D_REFERENCE, D_REFERENCE_ERROR))

        d_reference = strain.get_d_reference()
        np.testing.assert_equal(d_reference.values, D_REFERENCE)
        np.testing.assert_equal(d_reference.errors, D_REFERENCE_ERROR)

    def test_set_d_reference(self, strain_object_0, strain_object_1, strain_object_2,
                             strain_stress_object_0, strain_stress_object_1):
        r"""
        Test using a ScalarFieldSample
        strain_object_0: StrainField object made up of one StrainFieldSingle object
        strain_object_1: StrainField object made up of two non-overlapping StrainFieldSingle object
        strain_object_2: StrainField object made up of two overlapping StrainFieldSingle objects
        strain_stress_object_0: strains stacked, all have the same set of sample points
        """
        for strain, expected in [(strain_object_0, [1.00, 1.01, 1.02, 1.03, 1.04, 1.05, 1.06, 1.07]),
                                 (strain_object_1, [1.01, 1.02, 1.03, 1.04, 1.05, 1.06, 1.07, 1.08]),
                                 (strain_object_2, [1.01, 1.02, 1.03, 1.04, 1.05, 1.06, 1.07, 1.08])]:
            d_spacing = strain.get_dspacing_center()
            assert_allclose(d_spacing.values, expected, atol=0.001)
            # Set the reference spacings as the observed lattice plane spacings
            strain.set_d_reference(d_spacing)
            assert_allclose(strain.get_d_reference().values, expected)
            # There should be no strain, since the observed lattice plane spacings are the reference spacings
            assert_allclose(strain.values, np.zeros(8), atol=1.e-5)
        #
        # Use a new d_reference defined over a set of sample points having no overlap. In this case,
        # the d_reference of the strains should be left untouched
        d_reference_update = ScalarFieldSample('d_reference',
                                               values=[9, 9, 9], errors=[0.0, 0.0, 0.0],
                                               x=[9, 9, 9], y=[0, 0, 0], z=[0, 0, 0])
        for strain in (strain_object_0, strain_object_1, strain_object_2):
            d_reference_old = strain.get_d_reference()
            strain.set_d_reference(d_reference_update)  # no effect
            assert_allclose(strain.get_d_reference().values, d_reference_old.values)
        #
        # Use a new d_reference defined over a set of sample points corresponding to the last
        # three points of the strain field
        for strain in (strain_object_0,):
            d_reference_update = ScalarFieldSample('d_reference',
                                                   values=[9, 9, 9], errors=[0.0, 0.0, 0.0],
                                                   x=strain.x[-3:], y=strain.y[-3:], z=strain.z[-3:])
            d_reference_old = strain.get_d_reference()
            strain.set_d_reference(d_reference_update)  # affects only the last three points
            assert_allclose(strain.get_d_reference().values[: -3], d_reference_old.values[: -3])
            assert_allclose(strain.get_d_reference().values[-3:], [9, 9, 9])

        #
        # Use a new d_reference defined over a set of sample points corresponding to the last
        # three points of the stacked strains in strain_stress_object_0
        strains = strain_stress_object_0['strains']
        pl = strains['11'].point_list
        d_reference_update = ScalarFieldSample('d_reference',
                                               values=[9, 9, 9], errors=[0.0, 0.0, 0.0],
                                               x=pl.vx[-3:], y=pl.vy[-3:], z=pl.vz[-3:])
        for strain in strains.values():  # `strains` is a dictionary
            d_reference_old = strain.get_d_reference()
            strain.set_d_reference(d_reference_update)  # affects only the last three points
            assert_allclose(strain.get_d_reference().values[: -3], d_reference_old.values[: -3])
            assert_allclose(strain.get_d_reference().values[-3:], [9, 9, 9])

    def test_stack_strains(self, strain_field_samples, allclose_with_sorting):
        strain1 = strain_field_samples['HB2B_1320_peak0']
        strain2 = strain_field_samples['HB2B_1320_']

        # Stack two strains having the same evaluation points.
        strain1_stacked, strain2_stacked = strain1 * strain2  # default resolution and stacking mode
        for strain in (strain1_stacked, strain2_stacked):
            assert len(strain) == len(strain1)
            assert bool(np.all(np.isfinite(strain.values))) is True  # all points are common to strain1 and strain2

        # Stack two strains having completely different evaluation points.
        strain3 = strain_field_samples['strain with two points per direction']
        strain2_stacked, strain3_stacked = strain2 * strain3  # default resolution and stacking mode
        # The common list of points is the sum of the points from each strain
        for strain in (strain2_stacked, strain3_stacked):
            assert len(strain) == len(strain2) + len(strain3)

        # verify the filenames got copied over
        for strain_stacked, strain in ((strain2_stacked, strain2), (strain3_stacked, strain3)):
            assert strain_stacked.filenames == strain.filenames

        # There's no common point that is common to both strain2 and strain3
        # Each stacked strain only have finite measurements on points coming from the un-stacked strain
        for strain_stacked, strain in ((strain2_stacked, strain2), (strain3_stacked, strain3)):
            finite_measurements_count = len(np.where(np.isfinite(strain_stacked.values))[0])
            assert finite_measurements_count == len(strain)

        # The points evaluated as 'nan' must come from the other scan
        for strain_stacked, strain_other in ((strain2_stacked, strain3), (strain3_stacked, strain2)):
            nan_measurements_count = len(np.where(np.isnan(strain_stacked.values))[0])
            assert nan_measurements_count == len(strain_other)

    def test_fuse_and_stack_strains(self, strain_field_samples, allclose_with_sorting):
        # TODO HB2B_1320_peak0 and HB2B_1320_ are the same scan. We need two different scans
        strain1 = strain_field_samples['HB2B_1320_peak0']
        strain2 = strain_field_samples['HB2B_1320_']
        strain3 = strain_field_samples['strain with two points per direction']
        strain1_stacked, strain23_stacked = strain1 * (strain2 + strain3)  # default resolution and stacking mode
        # Check number of points with finite strains measuments
        for strain_stacked in (strain1_stacked, strain23_stacked):
            assert len(strain_stacked) == len(strain2) + len(strain3)
        for strain_stacked, finite_count, nan_count in zip((strain1_stacked, strain23_stacked), (312, 320), (8, 0)):
            finite_measurements_count = len(np.where(np.isfinite(strain_stacked.values))[0])
            assert finite_measurements_count == finite_count
            nan_measurements_count = len(np.where(np.isnan(strain_stacked.values))[0])
            assert nan_measurements_count == nan_count
        # Check peak collections carry-over
        assert strain1_stacked.peak_collections[0] == strain1.peak_collections[0]
        assert strain23_stacked.peak_collections == [strain2.peak_collections[0], strain3.peak_collections[0]]

    def test_to_md_histo_workspace(self, strain_field_samples):
        strain = strain_field_samples['HB2B_1320_peak0']
        histo = strain.to_md_histo_workspace(method='linear', resolution=DEFAULT_POINT_RESOLUTION)
        assert histo.id() == 'MDHistoWorkspace'
        minimum_values = (-31.76, -7.20, -15.00)  # bin boundary with the smallest coordinate along X, Y, and Z
        maximum_values = (31.76, 7.20, 15.00)  # bin boundary with the largest coordinate along X, Y, and Z
        bin_counts = (18, 6, 3)  # number of bins along  X, Y, and Z
        for i, (min_value, max_value, bin_count) in enumerate(zip(minimum_values, maximum_values, bin_counts)):
            dimension = histo.getDimension(i)
            assert dimension.getUnits() == 'mm'
            assert dimension.getMinimum() == pytest.approx(min_value, abs=0.01)
            assert dimension.getMaximum() == pytest.approx(max_value, abs=0.01)
            assert dimension.getNBins() == bin_count


def test_calculated_strain():
    SIZE = 10

    peaks = PeakCollectionLite('dummy',
                               strain=np.zeros(SIZE, dtype=float),
                               strain_error=np.zeros(SIZE, dtype=float))
    pointlist = PointList([np.arange(SIZE, dtype=float), np.arange(SIZE, dtype=float), np.arange(SIZE, dtype=float)])
    strain = StrainField(point_list=pointlist, peak_collection=peaks)
    np.testing.assert_equal(strain.values, 0.)


def strain_instantiator(name, values, errors, x, y, z):
    return StrainField(name,
                       peak_collection=PeakCollectionLite(name, strain=values, strain_error=errors),
                       point_list=PointList([x, y, z]))


@pytest.fixture(scope='module')
def strains_for_stress_field_1():
    X = [0.000, 1.000, 2.000, 3.000, 4.000, 5.000, 6.000, 7.000, 8.000, 9.000]
    Y = [0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000]
    Z = [0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000]
    # selected to make terms drop out

    sample11 = strain_instantiator('strain',
                                   [0.000, 0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.080, 0.009],  # values
                                   [0.000, 0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.009],  # errors
                                   X, Y, Z)
    sample22 = strain_instantiator('strain',
                                   [0.000, 0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.080, 0.009],  # values
                                   [0.000, 0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.009],  # errors
                                   X, Y, Z)
    sample33 = strain_instantiator('strain',
                                   [0.000, 0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.080, 0.009],  # values
                                   [0.000, 0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.009],  # errors
                                   X, Y, Z)
    return sample11, sample22, sample33


@pytest.fixture(scope='module')
def stress_samples(strains_for_stress_field_1):
    POISSON = 1. / 3.  # makes nu / (1 - 2*nu) == 1
    YOUNG = 1 + POISSON  # makes E / (1 + nu) == 1
    sample11, sample22, sample33 = strains_for_stress_field_1
    return {'stress diagonal': StressField(sample11, sample22, sample33, YOUNG, POISSON)}


class TestStressField:

    def test_strain_properties(self, strains_for_stress_field_1):
        field = StressField(*strains_for_stress_field_1, 1, 1)
        field.select('11')
        assert field.strain11 == field._strain11
        assert field.strain22 == field._strain22
        assert field.strain33 == field._strain33
        assert field.strain == field._strain11  # the accessible direction is still 11

    def test_getitem(self, strains_for_stress_field_1):
        field = StressField(*strains_for_stress_field_1, 1, 1)
        field.select('11')
        assert field['11'] == field.stress11
        assert field['22'] == field.stress22
        assert field['33'] == field.stress33
        assert field.stress == field.stress11

    def test_iter(self, strains_for_stress_field_1):
        field = StressField(*strains_for_stress_field_1, 1, 1)
        field.select('11')
        for stress_from_iterable, stress_component in zip(field, (field.stress11, field.stress22, field.stress33)):
            assert stress_from_iterable == stress_component
        assert field.stress == field.stress11  # the accessible direction is still 11

    def test_point_list(self, strains_for_stress_field_1):
        r"""Test point_list property"""
        vx = [0.000, 1.000, 2.000, 3.000, 4.000, 5.000, 6.000, 7.000, 8.000, 9.000]
        vy = [0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000]
        vz = [0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000]
        coordinates = np.array([vx, vy, vz]).T
        field = StressField(*strains_for_stress_field_1, 1.0, 1.0)
        np.allclose(field.coordinates, coordinates)

    def test_youngs_modulus(self, strains_for_stress_field_1):
        r"""Test poisson_ratio property"""
        youngs_modulus = random.random()
        field = StressField(*strains_for_stress_field_1, youngs_modulus, 1.0)
        assert field.youngs_modulus == pytest.approx(youngs_modulus)

    def test_youngs_modulus_setter(self, strain_stress_object_0):
        stress = strain_stress_object_0['stresses']['diagonal']
        assert_allclose(stress.stress11.values, [300, 340, 380, 420, 460], atol=1)
        assert_allclose(stress.stress22.values, [400, 440, 480, 520, 560], atol=1)
        assert_allclose(stress.stress33.values, [500, 540, 580, 620, 660], atol=1)
        stress.youngs_modulus *= 2.0
        assert stress.youngs_modulus == pytest.approx(8. / 3)
        assert_allclose(stress.stress11.values, 2 * np.array([300, 340, 380, 420, 460]), atol=1)
        assert_allclose(stress.stress22.values, 2 * np.array([400, 440, 480, 520, 560]), atol=1)
        assert_allclose(stress.stress33.values, 2 * np.array([500, 540, 580, 620, 660]), atol=1)

    def test_poisson_ratio(self, strains_for_stress_field_1):
        r"""Test poisson_ratio property"""
        poisson_ratio = random.random()
        field = StressField(*strains_for_stress_field_1, 1.0, poisson_ratio)
        assert field.poisson_ratio == pytest.approx(poisson_ratio)

    def test_poisson_ratio_setter(self, strain_stress_object_0):
        stress = strain_stress_object_0['stresses']['diagonal']
        assert_allclose(stress.stress11.values, [300, 340, 380, 420, 460], atol=1)
        assert_allclose(stress.stress22.values, [400, 440, 480, 520, 560], atol=1)
        assert_allclose(stress.stress33.values, [500, 540, 580, 620, 660], atol=1)
        strains = strain_stress_object_0['strains']
        stress.poisson_ratio = 0.0
        assert stress.poisson_ratio == pytest.approx(0.0)
        assert_allclose(stress.stress11.values, to_megapascal(stress.youngs_modulus * strains['11'].values), atol=1)
        assert_allclose(stress.stress22.values, to_megapascal(stress.youngs_modulus * strains['22'].values), atol=1)
        assert_allclose(stress.stress33.values, to_megapascal(stress.youngs_modulus * strains['33'].values), atol=1)

    def test_create_stress_field(self, allclose_with_sorting):
        X = [0.000, 1.000, 2.000, 3.000, 4.000, 5.000, 6.000, 7.000, 8.000, 9.000]
        Y = [0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000]
        Z = [0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000]
        # selected to make terms drop out

        sample11 = strain_instantiator('strain',
                                       [0.000, 0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.009],
                                       [0.000, 0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.009],
                                       X, Y, Z)
        sample22 = strain_instantiator('strain',
                                       [0.010, 0.011, 0.012, 0.013, 0.014, 0.015, 0.016, 0.017, 0.018, 0.019],
                                       [0.000, 0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.009],
                                       X, Y, Z)
        sample33 = strain_instantiator('strain',
                                       [0.020, 0.021, 0.022, 0.023, 0.024, 0.025, 0.026, 0.027, 0.028, 0.029],
                                       [0.000, 0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.009],
                                       X, Y, Z)

        POISSON = 1. / 3.  # makes nu / (1 - 2*nu) == 1
        YOUNG = 1 + POISSON  # makes E / (1 + nu) == 1

        # The default stress type is "diagonal", thus strain33 cannot be None
        with pytest.raises(AssertionError) as exception_info:
            StressField(sample11, sample22, None, YOUNG, POISSON)
        assert 'strain33 is None' in str(exception_info.value)

        # test diagonal calculation
        diagonal = StressField(sample11, sample22, sample33, YOUNG, POISSON)
        assert diagonal
        # check strains
        for direction, sample in zip(('11', '22', '33'), (sample11, sample22, sample33)):
            diagonal.select(direction)
            assert allclose_with_sorting(diagonal.strain.values, sample.values, atol=1)
        # check coordinates
        assert allclose_with_sorting(diagonal.x, X)
        assert allclose_with_sorting(diagonal.y, Y)
        assert allclose_with_sorting(diagonal.z, Z)
        # check values
        second = (sample11.values + sample22.values + sample33.values)
        diagonal.select('11')
        assert allclose_with_sorting(diagonal.values, to_megapascal(sample11.values + second), atol=1)
        diagonal.select('22')
        assert allclose_with_sorting(diagonal.values, to_megapascal(sample22.values + second), atol=1)
        diagonal.select('33')
        assert allclose_with_sorting(diagonal.values, to_megapascal(sample33.values + second), atol=1)

        in_plane_strain = StressField(sample11, sample22, None, YOUNG, POISSON, 'in-plane-strain')
        assert in_plane_strain
        # check coordinates
        assert allclose_with_sorting(in_plane_strain.x, X)
        assert allclose_with_sorting(in_plane_strain.y, Y)
        assert allclose_with_sorting(in_plane_strain.z, Z)
        # check values
        second = (sample11.values + sample22.values)
        in_plane_strain.select('11')
        allclose_with_sorting(in_plane_strain.values, to_megapascal(sample11.values + second), atol=1)
        in_plane_strain.select('22')
        allclose_with_sorting(in_plane_strain.values, to_megapascal(sample22.values + second), atol=1)
        in_plane_strain.select('33')
        allclose_with_sorting(in_plane_strain.values, to_megapascal(second), atol=1)
        # The strain along the 33 direction is zero by definition
        assert np.allclose(in_plane_strain.strain.values, [0.0] * in_plane_strain.size)
        assert np.allclose(in_plane_strain.strain.errors, [0.0] * in_plane_strain.size)

        # redefine values to simplify things
        POISSON = 1. / 2.  # makes nu / (1 - nu) == 1
        YOUNG = 1 + POISSON  # makes E / (1 + nu) == 1

        in_plane_stress = StressField(sample11, sample22, None, YOUNG, POISSON, 'in-plane-stress')
        assert in_plane_stress
        # check coordinates
        assert allclose_with_sorting(in_plane_stress.point_list.vx, X)
        assert allclose_with_sorting(in_plane_stress.point_list.vy, Y)
        assert allclose_with_sorting(in_plane_stress.point_list.vz, Z)
        # check values
        second = (sample11.values + sample22.values)
        in_plane_stress.select('11')
        strain11 = in_plane_stress.strain.values
        assert allclose_with_sorting(in_plane_stress.values, to_megapascal(sample11.values + second), atol=1)
        in_plane_stress.select('22')
        strain22 = in_plane_stress.strain.values
        assert allclose_with_sorting(in_plane_stress.values, to_megapascal(sample22.values + second), atol=1)
        in_plane_stress.select('33')
        strain33 = in_plane_stress.strain.values
        assert allclose_with_sorting(in_plane_stress.values, 0.)  # no stress on the 33 direction
        assert allclose_with_sorting(in_plane_stress.errors, 0.)
        factor = POISSON / (POISSON - 1)
        assert np.allclose(strain33, factor * (strain11 + strain22))

    def test_small(self):
        POISSON = 1. / 3.  # makes nu / (1 - 2*nu) == 1
        YOUNG = 1 + POISSON  # makes E / (1 + nu) == 1

        x = np.array([0.0, 0.5, 0.0, 0.5, 0.0, 0.5, 0.0, 0.5])
        y = np.array([1.0, 1.0, 1.5, 1.5, 1.0, 1.0, 1.5, 1.5])
        z = np.array([2.0, 2.0, 2.0, 2.0, 2.5, 2.5, 2.5, 2.5])
        point_list1 = PointList([x, y, z])
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
        errors = np.full(len(values), 1., dtype=float)
        strain = StrainField(peak_collection=PeakCollectionLite('strain', strain=values, strain_error=errors),
                             point_list=point_list1)

        # create a simple stress field
        stress = StressField(strain, strain, strain, YOUNG, POISSON)
        # Stress formulae with the above POISSON and YOUNG simplifies to:
        #   stress_ii = strain_ii + (strain_11 + strain_22 + strain_33).
        # Example: for the 11 direction we have:
        #   stress11 = 2 * strain11 + strain22 + strain33
        # Strains along different directions are independent, thus their errors add in quadrature
        #   stress11.errors = sqrt(4 * strain11.errors + strain22.errors + strain33.errors) == sqrt(6) * errors
        for direction in DIRECTIONS:
            stress.select(direction)
            assert stress.strain == strain  # it is the same reference
            # hand calculations show that this should be 4*strain
            assert_allclose(stress.values, 1000 * 4. * values)
            assert_allclose(stress.errors, 1000 * np.sqrt(6) * errors)

    def test_strain33_when_inplane_stress(self, strains_for_stress_field_1):
        sample11, sample22 = strains_for_stress_field_1[0:2]
        stress = StressField(sample11, sample22, None, 1.0, 2.0, 'in-plane-stress')
        assert np.allclose(stress._strain33.values, 2 * (stress._strain11.values + stress._strain22.values))

    def test_to_md_histo_workspace(self, stress_samples):
        stress = stress_samples['stress diagonal']
        histo = stress.to_md_histo_workspace(method='linear', resolution=DEFAULT_POINT_RESOLUTION)
        minimum_values = (-0.5, -0.0005, -0.0005)  # bin boundary with the smallest coordinate along X, Y, and Z
        maximum_values = (9.5, 0.0005, 0.0005)  # bin boundary with the largest coordinate along X, Y, and Z
        bin_counts = (10, 1, 1)  # number of bins along  X, Y, and Z
        assert histo.id() == 'MDHistoWorkspace'
        for i, (min_value, max_value, bin_count) in enumerate(zip(minimum_values, maximum_values, bin_counts)):
            dimension = histo.getDimension(i)
            assert dimension.getUnits() == 'mm'
            assert dimension.getMinimum() == pytest.approx(min_value, abs=0.01)
            assert dimension.getMaximum() == pytest.approx(max_value, abs=0.01)
            assert dimension.getNBins() == bin_count

    # flake8: noqa: C901
    def test_set_d_reference(self, strain_stress_object_0):
        #
        # Diagonal case
        stress = strain_stress_object_0['stresses']['diagonal']
        for direction in ('11', '22', '33'):
            stress.select(direction)
            # Use the spacings along the current direction as the new reference spacings
            d_reference_new = stress.strain.get_dspacing_center()
            stress.set_d_reference(d_reference_new)
            assert_allclose(stress.strain.get_d_reference().values, d_reference_new.values)
            # This direction should be free of strain because observed and reference spacings coincide
            assert_allclose(stress.strain.values, np.zeros(stress.size))
        # The current d_reference is the spacing along the last direction
        expected = np.array([1.20, 1.21, 1.22, 1.23, 1.24])
        for strain in stress.strain11, stress.strain22, stress.strain33:
            assert_allclose(strain.get_d_reference().values, expected, atol=0.001)
            assert_allclose(strain.values,
                            to_microstrain((strain.get_dspacing_center().values - expected) / expected), atol=1)
        # Stresses must be also be updated
        trace = stress.strain11.values + stress.strain22.values + stress.strain33.values
        for direction, strain in zip(('11', '22', '33'), (stress.strain11, stress.strain22, stress.strain33)):
            # Young's modulus and Poisson ratio for strain_stress_object_0 simplify the formulae
            assert_allclose(stress[direction].values, to_megapascal(strain.values + trace), atol=1)
        #
        # in-plane-strain case
        stress = strain_stress_object_0['stresses']['in-plane-strain']
        for direction in ('11', '22'):
            stress.select(direction)
            # Use the spacings along the current direction as the new reference spacings
            d_reference_new = stress.strain.get_dspacing_center()
            stress.set_d_reference(d_reference_new)
            assert_allclose(stress.strain.get_d_reference().values, d_reference_new.values)
            # This direction should be free of strain because observed and reference spacings coincide
            assert_allclose(stress.strain.values, np.zeros(stress.size))
            assert_allclose(stress.strain33.values, np.zeros(stress.size))  # because in-plane-strain
        # The current d_reference is the spacing along the '22' direction
        expected = np.array([1.10, 1.11, 1.12, 1.13, 1.14])
        for strain in stress.strain11, stress.strain22:
            assert_allclose(strain.get_d_reference().values, expected, atol=1)
            assert_allclose(strain.values,
                            to_microstrain((strain.get_dspacing_center().values - expected) / expected), atol=1)
        assert_allclose(stress.strain33.values, np.zeros(stress.size))  # because in-plane-strain
        # Stresses must be also be updated
        trace = stress.strain11.values + stress.strain22.values
        for direction, strain in zip(('11', '22', '33'), (stress.strain11, stress.strain22, stress.strain33)):
            # Young's modulus and Poisson ratio for strain_stress_object_0 simplify the formulae
            assert_allclose(stress[direction].values, to_megapascal(strain.values + trace), atol=1)
        #
        # in-plane-stress case
        stress = strain_stress_object_0['stresses']['in-plane-stress']
        for direction in ('11', '22'):
            stress.select(direction)
            # Use the spacings along the current direction as the new reference spacings
            d_reference_new = stress.strain.get_dspacing_center()
            stress.set_d_reference(d_reference_new)
            assert_allclose(stress.strain.get_d_reference().values, d_reference_new.values)
            # This direction should be free of strain because observed and reference spacings coincide
            assert_allclose(stress.strain.values, np.zeros(stress.size))
            # Young's modulus and Poisson ratio for strain_stress_object_0 simplify the formulae
            assert_allclose(stress.strain33.values, -(stress.strain11.values + stress.strain22.values))
            assert_allclose(stress['33'].values, np.zeros(stress.size))  # because in-plane-stress
        # The current d_reference is the spacing along the '22' direction
        expected = np.array([1.10, 1.11, 1.12, 1.13, 1.14])
        for strain in stress.strain11, stress.strain22:
            assert_allclose(strain.get_d_reference().values, expected, atol=1)
            assert_allclose(strain.values,
                            to_microstrain((strain.get_dspacing_center().values - expected) / expected), atol=1)
        assert_allclose(stress.strain33.values, -(stress.strain11.values + stress.strain22.values))
        # Stresses must be also be updated
        trace = stress.strain11.values + stress.strain22.values
        for direction, strain in zip(('11', '22'), (stress.strain11, stress.strain22)):
            # Young's modulus and Poisson ratio for strain_stress_object_0 simplify the formulae
            assert_allclose(stress[direction].values, to_megapascal(strain.values + trace), atol=1)
        assert_allclose(stress['33'].values, np.zeros(stress.size))  # because in-plane-stress
        # TODO also test with fixture strain_stress_object_1

    def test_strain_fields(self, strain_stress_object_1):
        r"""
        Test the values of the stacked strains along each direction as well as their components
        """
        stress = strain_stress_object_1['stresses']['diagonal']
        nanf = float('nan')

        # strain values for stacked strain along direction 11
        expected = to_microstrain([0.00, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, nanf, nanf])
        assert_allclose(stress.strain11.values, expected, equal_nan=True, atol=1)

        # strain values for stacked strain along direction 22
        expected = to_microstrain([nanf, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, nanf])
        # TODO bug: we obtain [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, nanf, nanf] instead of `expected`
        assert_allclose(stress.strain22.values, expected, equal_nan=True, atol=1)

        # strain values for stacked strain along direction 33
        expected = to_microstrain([nanf, nanf, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09])
        # TODO bug: we obtain [0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, nanf, nanf] instead of `expected`
        assert_allclose(stress.strain33.values, expected, equal_nan=True, atol=1)

        # strain values for the single strain along direction 11
        expected = to_microstrain([0.00, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07])
        assert_allclose(stress.strain11.strains[0].values, expected, equal_nan=True, atol=1)


@pytest.fixture(scope='module')
def field_sample_collection():
    return {
        'sample1': SampleMock('strain',
                              [1.000, 1.010, 1.020, 1.030, 1.040, 1.050, 1.060, 1.070, 1.080, 1.090],  # values
                              [0.000, 0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.009],  # errors
                              [0.000, 1.000, 2.000, 3.000, 4.000, 5.000, 6.000, 7.000, 8.000, 9.000],  # x
                              [0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000],  # y
                              [0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000]  # z
                              ),
        # distance resolution is assumed to be 0.01
        # The first four points of sample2 still overlaps with the first four points of sample1
        # the last four points of sample1 are not in sample2, and viceversa
        'sample2': SampleMock('strain',
                              [1.071, 1.081, 1.091, 1.10, 1.11, 1.12, 1.13, 1.14, 1.15, 1.16],  # values
                              [0.008, 0.008, 0.008, 0.00, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06],  # errors
                              [0.009, 1.009, 2.009, 3.009, 4.000, 5.000, 6.011, 7.011, 8.011, 9.011],  # x
                              [0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000],  # y
                              [0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000]  # z
                              ),
        # the last two points of sample3 are redundant, as they are within resolution distance
        'sample3': SampleMock('strain',
                              [1.000, 1.010, 1.020, 1.030, 1.040, 1.050, 1.060, 1.070, 1.080, 1.090, 1.091],  # values
                              [0.000, 0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.009, 0.008],  # errors
                              [0.000, 1.000, 2.000, 3.000, 4.000, 5.000, 6.000, 7.000, 8.000, 8.991, 9.000],  # x
                              [0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000],  # y
                              [0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000, 0.000]  # z
                              ),
    }


def test_aggregate_scalar_field_samples(field_sample_collection):
    sample1 = ScalarFieldSample(*field_sample_collection['sample1'])
    sample2 = ScalarFieldSample(*field_sample_collection['sample2'])
    sample3 = ScalarFieldSample(*field_sample_collection['sample3'])
    aggregated_sample = aggregate_scalar_field_samples(sample1, sample2, sample3)
    assert len(aggregated_sample) == len(sample1) + len(sample2) + len(sample3)
    # check some key field values
    assert aggregated_sample.values[len(sample1)] == pytest.approx(sample2.values[0])
    assert aggregated_sample.values[len(sample1) + len(sample2)] == pytest.approx(sample3.values[0])
    assert aggregated_sample.values[-1] == pytest.approx(sample3.values[-1])
    # check some key point coordinate values
    assert aggregated_sample.x[len(sample1)] == pytest.approx(sample2.x[0])
    assert aggregated_sample.x[len(sample1) + len(sample2)] == pytest.approx(sample3.x[0])
    assert aggregated_sample.x[-1] == pytest.approx(sample3.x[-1])


def test_fuse_scalar_field_samples(field_sample_collection):
    sample1 = ScalarFieldSample(*field_sample_collection['sample1'])
    sample2 = ScalarFieldSample(*field_sample_collection['sample2'])
    sample3 = ScalarFieldSample(*field_sample_collection['sample3'])
    fused_sample = fuse_scalar_field_samples(sample1, sample2, sample3, resolution=0.01, criterion='min_error')
    assert len(fused_sample) == 14
    assert sorted(fused_sample.values) == pytest.approx([1., 1.01, 1.02, 1.04, 1.05, 1.06, 1.07, 1.08,
                                                         1.091, 1.1, 1.13, 1.14, 1.15, 1.16])
    assert sorted(fused_sample.errors) == pytest.approx([0., 0., 0.001, 0.002, 0.004, 0.005, 0.006,
                                                         0.007, 0.008, 0.008, 0.03, 0.04, 0.05, 0.06])
    assert sorted(fused_sample.x) == pytest.approx([0.0, 1.0, 2.0, 3.009, 4.0, 5.0, 6.0, 6.011,
                                                    7.0, 7.011, 8.0, 8.011, 9.0, 9.011])


def test_mul(field_sample_collection, approx_with_sorting, allclose_with_sorting):
    # test stacking with the 'complete' mode
    sample1_unstacked = ScalarFieldSample(*field_sample_collection['sample1'])
    sample2_unstacked = ScalarFieldSample(*field_sample_collection['sample2'])
    sample3_unstacked = ScalarFieldSample(*field_sample_collection['sample3'])

    # stack using '*' operator
    sample1, sample2, sample3 = sample1_unstacked * sample2_unstacked * sample3_unstacked

    for sample in (sample1, sample2, sample3):
        assert len(sample) == 14
        approx_with_sorting(sample.x,
                            [5.0, 4.0, 3.003, 2.003, 1.003, 0.003, 9.0, 8.0, 6.0, 7.0, 9.011, 8.011, 6.011, 7.011])

    # Assert evaluations for sample1
    sample1_values = [1.05, 1.04, 1.03, 1.02, 1.01, 1.0,
                      1.09, 1.08, 1.06, 1.07,
                      float('nan'), float('nan'), float('nan'), float('nan')]
    assert allclose_with_sorting(sample1.values, sample1_values, equal_nan=True)

    # Assert evaluations for sample2
    sample2_values = [1.12, 1.11, 1.1, 1.091, 1.081, 1.071,
                      float('nan'), float('nan'), float('nan'), float('nan'),
                      1.16, 1.15, 1.13, 1.14]
    assert allclose_with_sorting(sample2.values, sample2_values, equal_nan=True)

    # Assert evaluations for sample3
    sample3_values = [1.05, 1.04, 1.03, 1.02, 1.01, 1.0,
                      1.091, 1.08, 1.06, 1.07,
                      float('nan'), float('nan'), float('nan'), float('nan')]
    assert allclose_with_sorting(sample3.values, sample3_values, equal_nan=True)


def test_stack_scalar_field_samples(field_sample_collection,
                                    approx_with_sorting, assert_almost_equal_with_sorting, allclose_with_sorting):
    r"""Stack three scalar fields"""
    # test stacking with the 'common' mode
    sample1 = ScalarFieldSample(*field_sample_collection['sample1'])
    sample2 = ScalarFieldSample(*field_sample_collection['sample2'])
    sample3 = ScalarFieldSample(*field_sample_collection['sample3'])
    sample1, sample2, sample3 = stack_scalar_field_samples(sample1, sample2, sample3, stack_mode='common')

    for sample in (sample1, sample2, sample3):
        assert len(sample) == 6
        assert_almost_equal_with_sorting(sample.x, [5.0, 4.0, 3.003, 2.003, 1.003, 0.003])

    # Assert evaluations for sample1
    sample1_values = [1.05, 1.04, 1.03, 1.02, 1.01, 1.0]
    assert allclose_with_sorting(sample1.values, sample1_values)
    # Assert evaluations for sample2
    sample2_values = [1.12, 1.11, 1.1, 1.091, 1.081, 1.071]
    assert allclose_with_sorting(sample2.values, sample2_values)
    # Assert evaluations for sample3
    sample3_values = [1.05, 1.04, 1.03, 1.02, 1.01, 1.0]
    assert allclose_with_sorting(sample3.values, sample3_values)

    # test stacking with the 'complete' mode
    sample1 = ScalarFieldSample(*field_sample_collection['sample1'])
    sample2 = ScalarFieldSample(*field_sample_collection['sample2'])
    sample3 = ScalarFieldSample(*field_sample_collection['sample3'])
    sample1, sample2, sample3 = stack_scalar_field_samples(sample1, sample2, sample3, stack_mode='complete')

    for sample in (sample1, sample2, sample3):
        assert len(sample) == 14
        approx_with_sorting(sample.x,
                            [5.0, 4.0, 3.003, 2.003, 1.003, 0.003, 9.0, 8.0, 6.0, 7.0, 9.011, 8.011, 6.011, 7.011])

    # Assert evaluations for sample1
    sample1_values = [1.05, 1.04, 1.03, 1.02, 1.01, 1.0,
                      1.09, 1.08, 1.06, 1.07,
                      float('nan'), float('nan'), float('nan'), float('nan')]
    assert allclose_with_sorting(sample1.values, sample1_values, equal_nan=True)

    # Assert evaluations for sample2
    sample2_values = [1.12, 1.11, 1.1, 1.091, 1.081, 1.071,
                      float('nan'), float('nan'), float('nan'), float('nan'),
                      1.16, 1.15, 1.13, 1.14]
    assert allclose_with_sorting(sample2.values, sample2_values, equal_nan=True)

    # Assert evaluations for sample3
    sample3_values = [1.05, 1.04, 1.03, 1.02, 1.01, 1.0,
                      1.091, 1.08, 1.06, 1.07,
                      float('nan'), float('nan'), float('nan'), float('nan')]
    assert allclose_with_sorting(sample3.values, sample3_values, equal_nan=True)


def test_stress_field_from_files(test_data_dir):
    HB2B_1320_PROJECT = os.path.join(test_data_dir, 'HB2B_1320.h5')
    YOUNG = 200.
    POISSON = 0.3

    # create 3 strain objects
    sample11 = StrainField(HB2B_1320_PROJECT)
    sample22 = StrainField(HB2B_1320_PROJECT)
    sample33 = StrainField(HB2B_1320_PROJECT)
    # create the stress field (with very uninteresting values
    stress = StressField(sample11, sample22, sample33, YOUNG, POISSON)

    # confirm the strains are unchanged
    for direction in DIRECTIONS:
        stress.select(direction)
        np.testing.assert_allclose(stress.strain.values,
                                   sample11.peak_collections[0].get_strain(units='microstrain')[0],
                                   atol=1, err_msg=f'strain direction {direction}')

    # calculate the values for stress
    strains = sample11.peak_collections[0].get_strain(units='microstrain')[0]
    stress_exp = strains + POISSON * (strains + strains + strains) / (1. - 2. * POISSON)
    stress_exp *= YOUNG / (1. + POISSON)

    # since all of the contributing strains are identical, everything else should match
    for direction in DIRECTIONS:
        stress.select(direction)
        np.testing.assert_equal(stress.point_list.coordinates, sample11.point_list.coordinates)
        np.testing.assert_allclose(stress.values, to_megapascal(stress_exp), atol=1,
                                   err_msg=f'stress direction {direction}')

    stress11 = stress.stress11.values
    print(stress11)
    assert np.all(np.logical_not(np.isnan(stress11)))  # confirm something was set

    # redo the calculation - this should change nothing
    stress.update_stress_calculation()
    np.testing.assert_equal(stress.stress11.values, stress11)

    # set the d-reference and see that the values are changed
    stress.set_d_reference((42., 0.))
    assert np.all(stress.stress11.values != stress11)


if __name__ == '__main__':
    pytest.main()
