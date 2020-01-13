from collections import namedtuple
import numpy as np

from pyrs.interface.peak_fitting.plot import Plot
from pyrs.dataobjects import HidraConstants
from pyrs.interface.peak_fitting.utilities import Utilities
from pyrs.interface.gui_helper import pop_message
from pyrs.interface.peak_fitting.gui_utilities import GuiUtilities
from pyrs.peaks import FitEngineFactory as PeakFitEngineFactory

PeakInfo = namedtuple('PeakInfo', 'center left_bound right_bound tag')


class Fit:

    def __init__(self, parent=None):
        self.parent = parent

    def fit_multi_peaks(self):

        # Get peak function and background function
        # peak_function_name = str(self.parent.ui.comboBox_peakType.currentText())
        # bkgd_function_name = str(self.parent.ui.comboBox_backgroundType.currentText())

        _peak_range_list = [tuple(_range) for _range in self.parent._ui_graphicsView_fitSetup.list_peak_ranges]
        _peak_center_list = [np.mean([left, right]) for (left, right) in _peak_range_list]
        _peak_tag_list = ["peak{}".format(_index) for _index, _ in enumerate(_peak_center_list)]
        _peak_function_name = str(self.parent.ui.comboBox_peakType.currentText())

        _peak_xmin_list = [left for (left, _) in _peak_range_list]
        _peak_xmax_list = [right for (_, right) in _peak_range_list]

        # Fit peak
        hd_ws = self.parent.hidra_workspace

        import pprint

        # _wavelength = self.parent._core.reduction_service._curr_workspace._wave_length_dict['1']
        _wavelength = 1.071
        hd_ws.set_wavelength(_wavelength, False)

        # print("_peak_range_list: {}".format(_peak_range_list))
        # print("_peak_center_list: {}".format(_peak_center_list))
        # print("_peak_tag_list: {}".format(_peak_tag_list))

        fit_engine = PeakFitEngineFactory.getInstance('Mantid', hd_ws, peak_function_name=_peak_function_name,
                                                             background_function_name='Linear')
        fit_result = fit_engine.fit_multiple_peaks(peak_tag_list=_peak_tag_list,
                                                   x_mins=_peak_xmin_list,
                                                   x_maxs=_peak_xmax_list)
        # result contains (peakcollections, fitted, difference)

        pprint.pprint("peak_collection_dict:")
        pprint.pprint(peak_collection_dict['peak0'])
        _peak = peak_collection_dict['peak0']
        pprint.pprint("_tag: {}".format(_peak._tag))
        pprint.pprint("_Params_error_array: {}".format(_peak._params_error_array))
        pprint.pprint("_value_array: {}".format(_peak._params_value_array))
        pprint.pprint("_fit_cost_array: {}".format(_peak._fit_cost_array))

        pprint.pprint("_core._peak_fitting_dict: {}".format(self.parent._core._peak_fitting_dict))

        pprint.pprint("HB2BReductionManager:")
        pprint.pprint(self.parent._core.reduction_service._curr_workspace._wave_length_dict)

        # show fitting parameters in table below 1D plot
        # self.show_fitting_parameters_in_table(peak_function=_peak_function_name,
        #                                       function_params=
        # plot fitted data

    def show_fitting_parameters_in_table(self):
        self.show_fit_result_table(peak_function='',
                                   function_params=None,
                                   fit_values=None)

    def fit_peaks(self, all_sub_runs=False):
        """ Fit peaks either all peaks or selected peaks
        The workflow includes
        1. parse sub runs, peak and background type
        2. fit peaks
        3. show the fitting result in table
        4. plot the peak in first sub runs that is fit
        :param all_sub_runs: Flag to fit peaks of all sub runs without checking
        :return:
        """
        # Get the sub runs to fit or all the peaks
        # if not all_sub_runs:
        #     # Parse sub runs specified in lineEdit_scanNumbers
        #     o_utilities = Utilities(parent=self.parent)
        #     sub_run_list = o_utilities.parse_sub_runs()
        # else:
        sub_run_list = None

        # Get peak function and background function
        peak_function = str(self.parent.ui.comboBox_peakType.currentText())
        bkgd_function = str(self.parent.ui.comboBox_backgroundType.currentText())

        # Get peak fitting range from the range of figure
        fit_range = self.parent._ui_graphicsView_fitSetup.get_x_limit()
        print('[INFO] Peak fit range: {0}'.format(fit_range))

        # Fit Peaks: It is better to fit all the peaks at the same time after testing
        guessed_peak_center = 0.5 * (fit_range[0] + fit_range[1])
        peak_info_dict = {'Peak 1': {'Center': guessed_peak_center, 'Range': fit_range}}
        self.parent._core.fit_peaks(project_name=self.parent._project_name,
                                    sub_run_list=sub_run_list,
                                    peak_type=peak_function,
                                    background_type=bkgd_function,
                                    peaks_fitting_setup=peak_info_dict)

        # Process fitted peaks
        # TEST - #84 - This shall be reviewed!
        try:
            # FIXME - effective_parameter=True will fail!
            # FIXME - other than return_format=dict will fail!
            # FIXME - need to give a real value to default_tag
            # FIXME - this only works if fitting 1 peak a time
            default_tag = peak_info_dict.keys()[0]
            function_params, fit_values = self.parent._core.get_peak_fitting_result(self.parent._project_name,
                                                                                    default_tag,
                                                                                    return_format=dict,
                                                                                    effective_parameter=False,
                                                                                    fitting_function=peak_function)
        except AttributeError as err:
            pop_message(self, 'Zoom in/out to only show peak to fit!', str(err), "error")
            return

        # TODO - #84+ - Need to implement the option as effective_parameter=True

        print('[DB...BAT...FITWINDOW....FIT] returned = {}, {}'.format(function_params, fit_values))

        self.parent._sample_log_names_mutex = True
        for param_name in function_params:
            self.parent._function_param_name_set.add(param_name)

        # # log index and center of mass
        # size_x = len(self.parent._sample_log_names) + len(self.parent._function_param_name_set) + 2
        #
        # # center of mass
        # size_y = len(self.parent._sample_log_names) + len(self.parent._function_param_name_set) + 1

        # release the mutex: because re-plot is required anyway
        self.parent._sample_log_names_mutex = False

        # Show fitting result in Table
        # TODO - could add an option to show native or effective peak parameters
        try:
            self.show_fit_result_table(peak_function, function_params, fit_values, is_effective=False)
        except IndexError:
            return

        # plot the model and difference
        if sub_run_list is None:
            o_plot = Plot(parent=self.parent)
            o_plot.plot_diff_and_fitted_data(1, True)

        o_gui = GuiUtilities(parent=self.parent)
        o_gui.set_1D_2D_axis_comboboxes(fill_fit=True)
        o_gui.enabled_export_csv_widgets(True)

    def show_fit_result_table(self, peak_function, peak_param_names, peak_param_dict, is_effective):
        """ Set up the table containing fit result
        :param peak_function: name of peak function
        :param peak_param_names: name of the parameters for the order of columns
        :param peak_param_dict: parameter names
        :param is_effective: Flag for the parameter to be shown as effective (True) or native (False)
        :return:
        """
        # Add peaks' centers of mass to the output table
        # peak_param_names.append(HidraConstants.PEAK_COM)
        # com_vec = self.parent._core.get_peak_center_of_mass(self.parent._project_name)
        # peak_param_dict[HidraConstants.PEAK_COM] = com_vec

        # Initialize the table by resetting the column names
        self.parent.ui.tableView_fitSummary.reset_table(peak_param_names)

        # Get sub runs for rows in the table
        sub_run_vec = peak_param_dict[HidraConstants.SUB_RUNS]

        # Add rows to the table for parameter information
        for row_index in range(sub_run_vec.shape[0]):
            # Set fit result
            self.parent.ui.tableView_fitSummary.set_fit_summary(row_index, peak_param_names,
                                                                peak_param_dict,
                                                                write_error=False,
                                                                peak_profile=peak_function)

    def initialize_fitting_table(self):
        # Set the table
        if self.parent.ui.tableView_fitSummary.rowCount() > 0:
            self.parent.ui.tableView_fitSummary.remove_all_rows()

        o_utility = Utilities(parent=self.parent)
        sub_run_list = o_utility.get_subruns_limit(self.parent._project_name)
        self.parent.ui.tableView_fitSummary.init_exp(sub_run_list)
