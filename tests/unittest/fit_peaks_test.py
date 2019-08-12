#!/user/bin/python
# Test class and methods implemented for peak fitting
import os
import numpy
from pyrs.core import pyrscore
from pyrs.core import instrument_geometry
from pyrs.utilities import script_helper
from matplotlib import pyplot as plt


class PeakFittingTest(object):
    """
    Class to test peak fitting related classes and methods
    """
    def __init__(self, input_file_name):
        """ Initialization
        :param input_file_name: name of testing HIDRA project file
        """
        # Create calibration control
        self._reduction_controller = pyrscore.PyRsCore()

        # Load data
        self._project_name = 'NFRS2 Peaks'
        self._reduction_controller.load_hidra_project(input_file_name, project_name=self._project_name,
                                                      load_detector_counts=False,
                                                      load_diffraction=True)

        return

    def fit_pseudo_voigt(self):
        """
        Fit pseudo-voigt peaks
        :return:
        """
        # Fit peaks
        self._reduction_controller.fit_peaks(self._project_name, sub_run_list=None,
                                             peak_type='PseudoVoigt', background_type='Linear',
                                             fit_range=(70., 95.))

        # Save result with default value on file name to import from and export to
        self._reduction_controller.save_peak_fit_result(self._project_name, src_rs_file_name=None,
                                                        target_rs_file_name=None)

        return


def main():
    """
    Test main
    :return:
    """
    test_project_file_name = ''

    # Create tester
    tester = PeakFittingTest(test_project_file_name)

    tester.fit_pseudo_voigt()

    return


if __name__ == '__main__':
    main()

