import os
from pyrs.core.nexus_conversion import NeXusConvertingApp
from pyrs.core.powder_pattern import ReductionApp
from pyrs.dataobjects import HidraConstants
from matplotlib import pyplot as plt
import numpy as np
import pytest

DIAGNOSTIC_PLOTS = False


def checkFileExists(filename, feedback):
    '''``feedback`` should be 'skip' to skip the test if it doesn't exist,
    or 'assert' to throw an AssertionError if the file doesn't exist
    '''
    if os.path.exists(filename):
        return

    message = 'File "{}" does not exist'.format(filename)
    if feedback == 'skip':
        pytest.skip(message)
    elif feedback == 'assert':
        raise AssertionError(message)
    else:
        raise ValueError('Do not know how to give feedback={}'.format(feedback))


def convertNeXusToProject(nexusfile, projectfile, skippable, mask_file_name=None):
    '''
    Parameters
    ==========
    nexusfile: str
        Path to Nexus file to reduce
    projectfile: str or None
        Path to the project file to save. If this is :py:obj:`None`, then the project file is not created
    skippable: bool
        Whether missing the nexus file skips the test or fails it
    mask_file_name: str
        Name of the masking file to use
    :return:
    '''
    if skippable:
        checkFileExists(nexusfile, feedback='skip')
    else:
        checkFileExists(nexusfile, feedback='assert')

    # remove the project file if it currently exists
    if projectfile and os.path.exists(projectfile):
        os.remove(projectfile)

    converter = NeXusConvertingApp(nexusfile, mask_file_name=mask_file_name)
    hidra_ws = converter.convert(use_mantid=False)
    if projectfile is not None:
        converter.save(projectfile)
        # tests for the created file
        assert os.path.exists(projectfile), 'Project file {} does not exist'.format(projectfile)

    return hidra_ws


def addPowderToProject(projectfile, use_mantid_engine=False, calibration_file=None):
    checkFileExists(projectfile, feedback='assert')

    # extract the powder patterns and add them to the project file
    reducer = ReductionApp(use_mantid_engine=use_mantid_engine)
    # TODO should add versions for testing arguments: instrument_file, calibration_file, mask, sub_runs
    reducer.load_project_file(projectfile)
    reducer.reduce_data(sub_runs=None, instrument_file=None, calibration_file=calibration_file, mask=None)
    reducer.save_diffraction_data(projectfile)

    # tests for the created file
    assert os.path.exists(projectfile)


@pytest.mark.parametrize('nexusfile, projectfile',
                         [('/HFIR/HB2B/IPTS-22731/nexus/HB2B_439.nxs.h5', 'HB2B_439.h5'),  # file when reactor was off
                          ('/HFIR/HB2B/IPTS-22731/nexus/HB2B_931.nxs.h5', 'HB2B_931.h5'),  # Vanadium
                          ('data/HB2B_938.nxs.h5', 'HB2B_938.h5')],  # A good peak
                         ids=('HB2B_439', 'HB2B_931', 'RW_938'))
def test_nexus_to_project(nexusfile, projectfile):
    """Test converting NeXus to project and convert to diffraction pattern

    Note: project file cannot be the same as NeXus file as the output file will be
    removed by pytest

    Parameters
    ----------
    nexusfile
    projectfile

    Returns
    -------

    """
    # convert the nexus file to a project file and do the "simple" checks
    try:
        test_hidra_ws = convertNeXusToProject(nexusfile, projectfile, skippable=True)
    except RuntimeError as run_err:
        if str(run_err).count('has no count') > 0:
            pytest.skip('{} has not count and thus not supported now'.format(nexusfile))
        else:
            raise run_err

    # verify sub run duration
    sub_runs = test_hidra_ws.get_sub_runs()
    durations = test_hidra_ws.get_sample_log_values(HidraConstants.SUB_RUN_DURATION, sub_runs=sub_runs)
    plt.plot(sub_runs, durations)

    if projectfile == 'HB2B_439.h5':
        np.testing.assert_equal(sub_runs, [1, 2, 3, 4])
        # TODO last value probably isn't right
        np.testing.assert_allclose(durations, [10, 5, 10, 17], atol=.1)

    # extract the powder patterns and add them to the project file
    addPowderToProject(projectfile, use_mantid_engine=False)

    # cleanup
    os.remove(projectfile)


@pytest.mark.parametrize('mask_file_name, filtered_counts, histogram_counts',
                         [('data/HB2B_Mask_12-18-19.xml', (540461, 1635432, 1193309), (510.8, 1555.7, 1136.3)),
                          (None, (548953, 1661711, 1212586), (518.7, 1580.5, 1154.4))],
                         ids=('HB2B_1017_Masked', 'HB2B_1017_NoMask'))
def test_reduce_data(mask_file_name, filtered_counts, histogram_counts):
    """Verify NeXus converters including counts and sample log values"""
    SUBRUNS = (1, 2, 3)
    CENTERS = (69.99525,  80.,  97.50225)

    # reduce with PyRS/Python
    hidra_ws = convertNeXusToProject('/HFIR/HB2B/IPTS-22731/nexus/HB2B_1017.nxs.h5', projectfile=None, skippable=True,
                                     mask_file_name=mask_file_name)

    # verify subruns
    np.testing.assert_equal(hidra_ws.get_sub_runs(), SUBRUNS)

    for sub_run, total_counts in zip(hidra_ws.get_sub_runs(), filtered_counts):
        counts_array = hidra_ws.get_detector_counts(sub_run)
        np.testing.assert_equal(counts_array.shape, (1048576,))
        assert np.sum(counts_array) == total_counts, 'mismatch in subrun={} for filtered data'.format(sub_run)

    # Test reduction to diffraction pattern
    reducer = ReductionApp(False)
    reducer.load_hidra_workspace(hidra_ws)
    reducer.reduce_data(sub_runs=None, instrument_file=None, calibration_file=None, mask=None)

    # plot the patterns
    if DIAGNOSTIC_PLOTS:
        from matplotlib import pyplot as plt
        for sub_run, angle in zip(SUBRUNS, CENTERS):
            x, y = reducer.get_diffraction_data(sub_run)
            plt.plot(x, y, label='SUBRUN {} at {:.1f} deg'.format(sub_run, angle))
        plt.legend()
        plt.show()

    # check ranges and total counts
    for sub_run, angle, total_counts in zip(SUBRUNS, CENTERS, histogram_counts):
        assert_label = 'mismatch in subrun={} for histogrammed data'.format(sub_run)
        x, y = reducer.get_diffraction_data(sub_run)
        assert x[0] < angle < x[-1], assert_label
        assert np.isnan(np.sum(y)), assert_label
        np.testing.assert_almost_equal(np.nansum(y), total_counts, decimal=1, err_msg=assert_label)

    # TODO add checks for against golden version


def test_split_log_time_average():
    """(Integration) test on doing proper time average on split sample logs

    Run-1086 was measured with moving detector (changing 2theta value) along sub runs.

    Returns
    -------

    """
    # Convert the NeXus to project
    nexus_file = '/HFIR/HB2B/IPTS-22731/nexus/HB2B_1086.nxs.h5'
    project_file = 'HB2B_1086.h5'
    convertNeXusToProject(nexus_file, project_file, skippable=True)


@pytest.mark.parametrize('project_file, van_project_file, target_project_file',
                         [('data/HB2B_938.h5', 'data/HB2B_931.h5', 'HB2B_938_van.h5')],
                         ids=['HB2B_938V'])
def test_apply_vanadium(project_file, van_project_file, target_project_file):
    """Test applying vanadium to the raw data in project file

    Parameters
    ----------
    project_file : str
        raw HiDRA project file to convert to 2theta pattern
    van_project_file : str
        raw HiDra vanadium file
    target_project_file : str
        target HiDRA

    Returns
    -------

    """
    # Check files' existence
    checkFileExists(project_file, feedback='assert')
    checkFileExists(van_project_file, feedback='assert')

    # Load data
    # extract the powder patterns and add them to the project file
    reducer = ReductionApp(use_mantid_engine=False)
    # instrument_file, calibration_file, mask, sub_runs
    reducer.load_project_file(project_file)
    reducer.reduce_data(sub_runs=None, instrument_file=None, calibration_file=None, mask=None,
                        van_file=van_project_file, num_bins=950)
    reducer.save_diffraction_data(target_project_file)

    # plot for proof
    # reducer.plot_reduced_data()


def test_apply_mantid_mask():
    """Test auto reduction script with Mantid mask file applied

    Returns
    -------

    """
    # Specify NeXus
    nexus_file = 'data/HB2B_938.nxs.h5'

    # Convert the NeXus to file to a project without mask and convert to 2theta diffraction pattern
    no_mask_project_file = 'HB2B_938_no_mask.h5'
    no_mask_hidra_ws = convertNeXusToProject(nexus_file, no_mask_project_file, skippable=False,
                                             mask_file_name=None)

    mask_array = no_mask_hidra_ws.get_detector_mask(is_default=True)
    assert mask_array is None, 'There shall not be any mask'

    # Convert the nexus file to a project file and do the "simple" checks
    no_mask_reducer = ReductionApp(use_mantid_engine=False)
    no_mask_reducer.load_project_file(no_mask_project_file)
    no_mask_reducer.reduce_data(sub_runs=None, instrument_file=None, calibration_file=None, mask=None,
                                van_file=None, num_bins=950)
    no_mask_reducer.save_diffraction_data(no_mask_project_file)

    # Convert the NeXus to file to a project with mask and convert to 2theta diffraction pattern
    project_file = 'HB2B_938_mask.h5'
    masked_hidra_ws = convertNeXusToProject(nexus_file, project_file, skippable=False,
                                            mask_file_name='data/HB2B_Mask_12-18-19.xml')
    mask_array = masked_hidra_ws.get_detector_mask(True)
    # check on Mask: num_masked_pixels = (135602,)
    assert np.where(mask_array == 0)[0].shape[0] == 135602, 'Mask shall have 135602 pixels masked but not {}' \
                                                            ''.format(np.where(mask_array == 0)[0].shape[0])

    reducer = ReductionApp(use_mantid_engine=False)
    reducer.load_project_file(project_file)
    # convert to diffraction pattern with mask
    reducer.reduce_data(sub_runs=None, instrument_file=None, calibration_file=None, mask=mask_array,
                        van_file=None, num_bins=950)
    reducer.save_diffraction_data(project_file)

    # Compare range of 2theta
    no_mask_data_set = no_mask_reducer.get_diffraction_data(sub_run=1)
    masked_data_set = reducer.get_diffraction_data(sub_run=1)

    print('[DEBUG...] No mask 2theta range: {}, {}'.format(no_mask_data_set[0].min(), no_mask_data_set[0].max()))
    print('[DEBUG...] Masked  2theta range: {}, {}'.format(masked_data_set[0].min(), masked_data_set[0].max()))

    # verify the masked reduced data shall have smaller or at least equal range of 2theta
    assert no_mask_data_set[0].min() <= masked_data_set[0].min()
    assert no_mask_data_set[0].max() >= masked_data_set[0].max()


def test_hidra_workflow(tmpdir):
    nexus = '/HFIR/HB2B/IPTS-22731/nexus/HB2B_1060.nxs.h5'
    mask = '/HFIR/HB2B/shared/CALIBRATION/HB2B_MASK_Latest.xml'
    calibration = '/HFIR/HB2B/shared/CALIBRATION/HB2B_Latest.json'
    project = os.path.basename(nexus).split('.')[0] + '.h5'
    project = os.path.join(str(tmpdir), project)
    try:
        _ = convertNeXusToProject(nexus, project, True, mask_file_name=mask)
        addPowderToProject(project, calibration_file=calibration)
    finally:
        if os.path.exists(project):
            os.remove(project)


if __name__ == '__main__':
    pytest.main([__file__])
