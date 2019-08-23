# Peak fitting engine by calling mantid
from pyrs.core import mantid_helper
from pyrs.utilities import checkdatatypes
from pyrs.core import peak_fit_engine
import numpy as np
import os
import math
from mantid.api import AnalysisDataService
from mantid.simpleapi import CreateWorkspace, FitPeaks


class MantidPeakFitEngine(peak_fit_engine.PeakFitEngine):
    """
    peak fitting engine class for mantid
    """
    def __init__(self, workspace, sub_run_list, mask_name):
        """ Initialization to set up the workspace for fitting
        :param workspace: Hidra workspace to get the diffraction peaks from
        :param sub_run_list: list of sun runs
        :param mask_name: Mask acting on the detector (i.e., referring to a specific set of diffraction data)
        """
        # call parent
        super(MantidPeakFitEngine, self).__init__(workspace, sub_run_list, mask_name)

        # sub-run, Mantid workspace index dictionary
        # self._ws_index_sub_run_dict = dict()

        # Create Mantid workspace: generate a workspace with all sub runs!!!
        self._mantid_workspace = mantid_helper.generate_mantid_workspace(workspace, mask_name)
        self._workspace_name = self._mantid_workspace.name()

        # some observed properties
        self._center_of_mass_ws_name = None
        self._highest_point_ws_name = None

        # fitting result (Mantid specific)
        self._fitted_peak_position_ws = None  # fitted peak position workspace
        self._fitted_function_param_table = None  # fitted function parameters table workspace
        self._fitted_function_error_table = None  # fitted function parameters' fitting error table workspace
        self._model_matrix_ws = None  # MatrixWorkspace of the model from fitted function parameters

        return

    def calculate_center_of_mass(self):
        """ calculate center of mass of peaks in the Mantid MatrixWorkspace as class variable
        and highest data point
        :return:
        """
        # get the workspace
        data_ws = AnalysisDataService.retrieve(self._workspace_name)
        num_spectra = data_ws.getNumberHistograms()

        peak_center_vec = np.ndarray(shape=(num_spectra, 2), dtype='float')

        for iws in range(num_spectra):
            vec_x = data_ws.readX(iws)
            vec_y = data_ws.readY(iws)
            com_i = np.sum(vec_x * vec_y) / np.sum(vec_y)
            peak_center_vec[iws, 0] = com_i
            imax_peak = np.argmax(vec_y, axis=0)
            peak_center_vec[iws, 1] = vec_x[imax_peak]

        # create 2 workspaces
        self._center_of_mass_ws_name = '{0}_COM'.format(self._workspace_name)
        com_ws = CreateWorkspace(DataX=peak_center_vec[:, 0], DataY=peak_center_vec[:, 0],
                                 NSpec=num_spectra, OutputWorkspace=self._center_of_mass_ws_name)
        print ('[INFO] Center of Mass Workspace: {0} Number of spectra = {1}'
               ''.format(self._center_of_mass_ws_name, com_ws.getNumberHistograms()))

        self._highest_point_ws_name = '{0}_HighestPoints'.format(self._workspace_name)
        high_ws = CreateWorkspace(DataX=peak_center_vec[:, 1], DataY=peak_center_vec[:, 1],
                                  NSpec=num_spectra, OutputWorkspace=self._highest_point_ws_name)
        print ('[INFO] Highest Point Workspace: {0} Number of spectra = {1}'
               ''.format(self._highest_point_ws_name, high_ws.getNumberHistograms()))

        self._peak_center_vec = peak_center_vec

        return

    def calculate_peak_position_d(self, wave_length_vec):
        """ Calculate peak positions in d-spacing
        :return:
        """
        # TODO/FIXME - #80+ - Must have a better way than try and guess
        try:
            r = self.get_fitted_params(param_name_list=['PeakCentre'], including_error=True)
        except KeyError:
            r = self.get_fitted_params(param_name_list=['centre'], including_error=True)
        sub_run_vec = r[0]
        params_vec = r[1]

        # init vector for peak center in d-spacing with error
        self._peak_center_d_vec = np.ndarray((params_vec.shape[1], 2), params_vec.dtype)

        for index in range(sub_run_vec.shape[0]):
            # convert to d-spacing: both fitted value and fitting error
            lambda_i = wave_length_vec[index]
            for sub_index in range(2):
                peak_i_2theta_j = params_vec[0][index][sub_index]
                peak_i_d_j = lambda_i * 0.5 / math.sin(peak_i_2theta_j * 0.5 * math.pi / 180.)
                self._peak_center_d_vec[index][sub_index] = peak_i_d_j

            # peak_i_2theta_std = centre_vec[index][1]
            # peak_i_d_std = lambda_i * 0.5 / math.sin(peak_i_2theta_std * 0.5 * math.pi / 180.)
            # self._peak_center_d_vec[index][0] = peak_i_d
            # self._peak_center_d_vec[index][1] = peak_i_d_std
        # END-FOR

        return

    def fit_peaks(self, peak_function_name, background_function_name, fit_range, scan_index=None):
        """
        fit peaks
        :param peak_function_name:
        :param background_function_name:
        :param fit_range:
        :param scan_index: single scan index to fit for.  If None, then fit for all spectra
        :return:
        """
        checkdatatypes.check_string_variable('Peak function name', peak_function_name)
        checkdatatypes.check_string_variable('Background function name', background_function_name)
        if scan_index is not None:
            checkdatatypes.check_int_variable('Scan (log) index', scan_index, value_range=[0, self.get_number_scans()])
            start = scan_index
            stop = scan_index
        else:
            start = 0
            stop = self.get_number_scans() - 1

        # check peak function name:
        if peak_function_name not in ['Gaussian', 'Voigt', 'PseudoVoigt', 'Lorentzian']:
            raise RuntimeError('Peak function {0} is not supported yet.'.format(peak_function_name))
        if background_function_name not in ['Linear', 'Flat']:
            raise RuntimeError('Background type {0} is not supported yet.'.format(background_function_name))

        data_workspace = self.retrieve_workspace(self._workspace_name, True)
        num_spectra = data_workspace.getNumberHistograms()
        peak_window_ws_name = 'fit_window_{0}'.format(self._workspace_name)
        CreateWorkspace(DataX=np.array([fit_range[0], fit_range[1]] * num_spectra),
                        DataY=np.array([fit_range[0], fit_range[1]] * num_spectra),
                        NSpec=num_spectra, OutputWorkspace=peak_window_ws_name)

        # fit
        print ('[DB...BAT] Data workspace # spec = {0}. Fit range = {1}'
               ''.format(num_spectra, fit_range))

        # no pre-determined peak center: use center of mass
        r_positions_ws_name = 'fitted_peak_positions_{0}'.format(self._workspace_name)
        r_param_table_name = 'param_m_{0}'.format(self._workspace_name)
        r_error_table_name = 'param_e_{0}'.format(self._workspace_name)
        r_model_ws_name = 'model_full_{0}'.format(self._workspace_name)

        # TODO - NOW - Requiring good estimation!!! - shall we use a dictionary to set up somewhere else?
        width_dict = {'Gaussian': ('Sigma', 0.36),
                      'PseudoVoigt': ('FWHM', 1.0),
                      'Voigt': ('LorentzFWHM, GaussianFWHM', '0.1, 0.7')}

        print ('[DB...BAT] Peak function: {}'.format(peak_function_name))
        print ('[DB...BAT] Param names:   {}'.format(width_dict[peak_function_name][0]))
        print ('[DB...BAT] Param values:  {}'.format(width_dict[peak_function_name][1]))

        # Get peak center workspace
        self.calculate_center_of_mass()

        args = dict()
        if self._center_of_mass_ws_name == '' or self._center_of_mass_ws_name is None:
            peak_centers = 85.
            args['PeakCenters'] = peak_centers
        else:
            args['PeakCentersWorkspace'] = self._center_of_mass_ws_name
            peak_centers = None

        r = FitPeaks(InputWorkspace=self._workspace_name,
                     OutputWorkspace=r_positions_ws_name,
                     PeakCentersWorkspace=self._center_of_mass_ws_name,
                     # PeakCenters=peak_centers,
                     PeakFunction=peak_function_name,
                     BackgroundType=background_function_name,
                     StartWorkspaceIndex=start,
                     StopWorkspaceIndex=stop,
                     FindBackgroundSigma=1,
                     HighBackground=False,
                     ConstrainPeakPositions=False,
                     PeakParameterNames=width_dict[peak_function_name][0],
                     PeakParameterValues=width_dict[peak_function_name][1],
                     RawPeakParameters=True,
                     OutputPeakParametersWorkspace=r_param_table_name,
                     OutputParameterFitErrorsWorkspace=r_error_table_name,
                     FittedPeaksWorkspace=r_model_ws_name,
                     FitPeakWindowWorkspace=peak_window_ws_name)

        # r is a class containing multiple outputs (workspaces)
        # print (r,  r.OutputParameterFitErrorsWorkspace.getColumnNames(), r.OutputPeakParametersWorkspace,
        #        r.FittedPeaksWorkspace)

        print ('[DB] Fit peaks parameters: range {0} - {1}.  Fit window boundary: {2} - {3}'
               ''.format(start, stop, fit_range[0], fit_range[1]))

        # Save all the workspaces automatically for further review
        if False:
            mantid_helper.study_mantid_peak_fitting()
        # END-IF-DEBUG (True)

        # process output
        self._fitted_peak_position_ws = AnalysisDataService.retrieve(r_positions_ws_name)
        self._fitted_function_param_table = AnalysisDataService.retrieve(r_param_table_name)
        self._fitted_function_error_table = AnalysisDataService.retrieve(r_error_table_name)
        self._model_matrix_ws = AnalysisDataService.retrieve(r_model_ws_name)

        return

    # def generate_matrix_workspace(self, data_set_list, matrix_ws_name):
    #     """ Convert data set of all scans to a multiple-spectra Mantid MatrixWorkspace
    #     :param data_set_list:
    #     :param matrix_ws_name
    #     :return:
    #     """
    #     # check input
    #     checkdatatypes.check_list('Data set list', data_set_list)
    #     checkdatatypes.check_string_variable('MatrixWorkspace name', matrix_ws_name)
    #
    #     # make ws-index sub-run map get ready
    #     self._ws_index_sub_run_dict.clear()
    #
    #     # convert input data set to list of vector X and vector Y
    #     vec_x_list = list()
    #     vec_y_list = list()
    #     for index in range(len(data_set_list)):
    #         # get data
    #         diff_data = data_set_list[index]
    #         vec_x = diff_data[0]
    #         vec_y = diff_data[1]
    #         # append
    #         vec_x_list.append(vec_x)
    #         vec_y_list.append(vec_y)
    #         # update ws-index to sub run map
    #         self._ws_index_sub_run_dict[index] = self._sub_run_list[index]  # maybe redundant
    #     # END-FOR
    #
    #     # create MatrixWorkspace
    #     datax = np.concatenate(vec_x_list, axis=0)
    #     datay = np.concatenate(vec_y_list, axis=0)
    #     ws_full = CreateWorkspace(DataX=datax, DataY=datay, NSpec=len(vec_x_list),
    #                               OutputWorkspace=matrix_ws_name)
    #
    #     return ws_full

    def get_observed_peaks_centers(self):
        """
        get center of mass vector and X value vector corresponding to maximum Y value
        :return:
        """
        return self._peak_center_vec

    # def get_peak_fit_parameters(self):
    #     """
    #     get fitted peak's parameters
    #     :return: dictionary of dictionary. level 0: key as scan index, value as dictionary
    #                                        level 1: key as parameter name such as height, cost, and etc
    #     """
    #     # TODO - 20181101 - Need to expand this method such that all fitted parameters will be added to output
    #     # get value
    #     scan_index_vector = self.get_scan_indexes()
    #     cost_vector = self.get_fitted_params(param_name_list='chi2')
    #     height_vector = self.get_fitted_params(param_name_list='height')
    #     width_vector = self.get_fitted_params(param_name_list='width')
    #
    #     # check
    #     if len(scan_index_vector) != len(cost_vector) or len(cost_vector) != len(height_vector) \
    #             or len(cost_vector) != len(width_vector):
    #         raise RuntimeError('Scan indexes ({0}) and cost/height/width ({1}/{2}/{3}) have different sizes.'
    #                            ''.format(len(scan_index_vector), len(cost_vector), len(height_vector),
    #                                      len(width_vector)))
    #
    #     # combine to dictionary
    #     fit_params_dict = dict()
    #     for index in range(len(scan_index_vector)):
    #         scan_log_index = scan_index_vector[index]
    #         fit_params_dict[scan_log_index] = dict()
    #         fit_params_dict[scan_log_index]['cost'] = cost_vector[index]
    #         fit_params_dict[scan_log_index]['height'] = height_vector[index]
    #         fit_params_dict[scan_log_index]['width'] = width_vector[index]
    #
    #     return fit_params_dict

    # def get_peak_intensities(self):
    #     """
    #     get peak intensities for each fitted peaks
    #     :return:
    #     """
    #     # get value
    #     scan_index_vector = self.get_scan_indexes()
    #     intensity_vector = self.get_fitted_params(param_name_list='intensity')
    #
    #     # check
    #     if len(scan_index_vector) != len(intensity_vector):
    #         raise RuntimeError('Scan indexes ({0}) and intensity ({1}) have different sizes.'
    #                            ''.format(len(scan_index_vector), len(intensity_vector)))
    #
    #     # combine to dictionary
    #     intensity_dict = dict()
    #     for index in range(len(scan_index_vector)):
    #         intensity_dict[scan_index_vector[index]] = intensity_vector[index]
    #
    #     return intensity_dict

    def get_calculated_peak(self, scan_log_index):
        """
        get the model (calculated) peak of a certain scan
        :param scan_log_index:
        :return:
        """
        if self._model_matrix_ws is None:
            raise RuntimeError('There is no fitting result!')

        checkdatatypes.check_int_variable('Scan log index', scan_log_index, (0, self._model_matrix_ws.getNumberHistograms()))

        vec_x = self._model_matrix_ws.readX(scan_log_index)
        vec_y = self._model_matrix_ws.readY(scan_log_index)

        return vec_x, vec_y

    def get_center_of_mass_workspace_name(self):
        """
        Get the center of mass workspace name
        :return:
        """
        return self._center_of_mass_ws_name

    def get_data_workspace_name(self):
        """
        get the data workspace name
        :return:
        """
        return self._workspace_name

    def _get_fitted_parameters_value(self, spec_index_vec, param_name_list, param_value_array):
        """
        Get fitted peak parameters' value
        :param spec_index_vec:
        :param param_name_list:
        :param param_value_array:
        :return:
        """
        # table column names
        col_names = self._fitted_function_param_table.getColumnNames()

        # get fitted parameter value
        for out_index, param_name in enumerate(param_name_list):
            # get value from column
            param_col_index = col_names.index(param_name)
            param_vec = self._fitted_function_param_table.column(param_col_index)
            # set value
            param_value_array[:, out_index] = param_vec
        # END-FOR

        return

    def get_fit_cost(self, max_chi2):
        """ Get the peak function cost
        :param max_chi2:
        :return:
        """
        # Get chi2 column
        col_names = self._fitted_function_param_table.getColumnNames()
        chi2_col_index = col_names.index('chi2')

        # TODO FIXME TEST - #80 - does this work?
        chi2_vec = self._fitted_function_param_table.column(chi2_col_index)

        # Filter out the sub runs/spectra with large chi^2
        if max_chi2 is not None and max_chi2 < 1.E20:
            # selected
            good_fit_indexes = np.where(chi2_vec < max_chi2)
            chi2_vec = chi2_vec[good_fit_indexes]
            spec_vec = good_fit_indexes[0]
        else:
            # all
            spec_vec = np.arange(chi2_vec.shape[0])

        return spec_vec, chi2_vec

    def get_fitted_params_x(self, param_name_list, including_error, max_chi2=1.E20):
        """ Get specified parameters' fitted value and optionally error with optionally filtered value
        :param param_name_list:
        :param including_error:
        :param max_chi2: Default is including all.
        :return: 2-tuple: (1) (n, ) vector for sub run number  (2) (p, n, 1) or (p, n, 2) vector for parameter values and
                 optionally fitting error: p = number of parameters , n = number of sub runs
        """
        # check
        checkdatatypes.check_list('Function parameters', param_name_list)
        checkdatatypes.check_bool_variable('Flag to output fitting error', including_error)
        checkdatatypes.check_float_variable('Maximum cost chi^2', max_chi2, (1, None))

        # get table information
        col_names = self._fitted_function_param_table.getColumnNames()
        chi2_col_index = col_names.index('chi2')
        ws_index_col_index = col_names.index('wsindex')

        # get the rows to survey
        if max_chi2 > 0.999E20:
            # all of sub runs / spectra
            row_index_list = range(self._fitted_function_param_table.rowCount())
        else:
            # need to filter: get a list of chi^2 and then filter
            chi2_vec = np.zeros(shape=(self._fitted_function_param_table.rowCount(),), dtype='float')
            for row_index in range(self._fitted_function_param_table.rowCount()):
                chi2_i = self._fitted_function_param_table.cell(row_index, chi2_col_index)
                chi2_vec[row_index] = chi2_i

            # filer chi2 against max
            filtered_indexes = np.where(chi2_vec < max_chi2)
            row_index_list = list(filtered_indexes)
        # END-IF-ELSE

        # init parameters
        num_params = len(param_name_list)
        if including_error:
            num_items = 2
        else:
            num_items = 1
        param_vec = np.zeros(shape=(num_params, len(row_index_list), num_items), dtype='float')
        sub_run_vec = np.zeros(shape=(len(row_index_list), ), dtype='int')

        # sub runs
        for vec_index, row_index in enumerate(row_index_list):
            # sub run
            ws_index_i = self._fitted_function_param_table.cell(row_index, ws_index_col_index)
            sub_run_i = self._ws_index_sub_run_dict[ws_index_i]
            sub_run_vec[vec_index] = sub_run_i
        # END-FOR

        # retrieve parameters
        for param_index, param_name_i in enumerate(param_name_list):
            # get the parameter column index
            if param_name_i in col_names:
                param_i_col_index = col_names.index(param_name_i)
            else:
                param_i_col_index = None

            # go through all the rows fitting the chi^2 requirement
            for vec_index, row_index in enumerate(row_index_list):
                # init error
                error_i = None

                if param_i_col_index is not None:
                    # native parameters
                    value_i = self._fitted_function_param_table.cell(row_index, param_i_col_index)
                    if including_error:
                        error_i = self._fitted_function_error_table.cell(row_index, param_i_col_index)
                elif param_name_i == 'center_d':
                    # special center in dSpacing
                    value_i = self._peak_center_d_vec[row_index]
                    if including_error:
                        error_i = self._peak_center_d_error_vec[row_index]
                elif param_name_i in self._effective_parameters:
                    # effective parameter
                    value_i = self.calculate_effective_parameter(param_name_i)
                    if including_error:
                        error_i = self.calculate_effective_parameter_error(param_name_i)
                else:
                    err_msg = 'Function parameter {0} does not exist. Supported parameters are {1}' \
                              ''.format(param_name_list, col_names)
                    # raise RuntimeError()
                    raise KeyError(err_msg)
                # END-IF-ELSE

                # set value
                param_vec[param_index, vec_index, 0] = value_i
                if including_error:
                    param_vec[param_index, vec_index, 1] = error_i
            # END-FOR (each row)
        # END-FOR (each parameter)

        return sub_run_vec, param_vec

    def get_scan_indexes(self):
        """
        get a vector of scan indexes and assume that the scan log indexes are from 0 and consecutive
        :return: vector of integer from 0 and up consecutively
        """
        data_workspace = self.retrieve_workspace(self._workspace_name, True)
        indexes_list = range(data_workspace.getNumberHistograms())

        return np.array(indexes_list)

    # def get_fitted_params_error(self, param_name):
    #     """ Get the value of a specified parameters's fitted error of whole scan
    #     Note: from FitPeaks's output workspace "OutputParameterFitErrorsWorkspace"
    #     :param param_name:
    #     :return: float vector of parameters...
    #     """
    #     # TODO - NOW - Continue (2) from here to sort out how do we demo result to front-end
    #     # check
    #     checkdatatypes.check_string_variable('Function parameter', param_name)
    #
    #     # init parameters
    #     error_vec = np.ndarray(shape=(self._fitted_function_error_table.rowCount()), dtype='float')
    #
    #     col_names = self._fitted_function_error_table.getColumnNames()
    #     if param_name in col_names:
    #         col_index = col_names.index(param_name)
    #         for row_index in range(self._fitted_function_error_table.rowCount()):
    #             error_vec[row_index] = self._fitted_function_error_table.cell(row_index, col_index)
    #     elif param_name == 'center_d':
    #         error_vec = self._peak_center_d_error_vec
    #     else:
    #         err_msg = 'Function parameter {0} does not exist. Supported parameters are {1}' \
    #                   ''.format(param_name, col_names)
    #         # raise RuntimeError()
    #         raise KeyError(err_msg)
    #
    #     return error_vec
    #
    # def get_good_fitted_params(self, param_name, max_chi2=1.E20):
    #     """
    #     get fitted parameter's value for good fit specified by maximum chi2
    #     :param param_name:
    #     :param max_chi2:
    #     :return: 2-vector of same size
    #     """
    #     # check
    #     checkdatatypes.check_string_variable('Function parameter', param_name)
    #     checkdatatypes.check_float_variable('Chi^2', max_chi2, (1., None))
    #
    #     # get all the column names
    #     col_names = self._fitted_function_param_table.getColumnNames()
    #     if not ('chi2' in col_names and (param_name in col_names or param_name == 'center_d')):
    #         err_msg = 'Function parameter {0} does not exist. Supported parameters are {1}' \
    #                   ''.format(param_name, col_names)
    #         # raise RuntimeError()
    #         raise KeyError(err_msg)
    #     elif param_name == 'chi2':
    #         is_chi2 = True
    #     else:
    #         is_chi2 = False
    #
    #     # get chi2 first
    #     chi2_col_index = col_names.index('chi2')
    #     if param_name == 'center_d':
    #         param_col_index = 'center_d'
    #     elif not is_chi2:
    #         param_col_index = col_names.index(param_name)
    #     else:
    #         param_col_index = chi2_col_index
    #
    #     param_list = list()
    #     selected_row_index = list()
    #     for row_index in range(self._fitted_function_param_table.rowCount()):
    #         chi2 = self._fitted_function_param_table.cell(row_index, chi2_col_index)
    #         if math.isnan(chi2) or chi2 > max_chi2:
    #             continue
    #
    #         if is_chi2:
    #             value_i = chi2
    #         elif param_col_index == 'center_d':
    #             value_i = self._peak_center_d_vec[row_index]
    #         else:
    #             value_i = self._fitted_function_param_table.cell(row_index, param_col_index)
    #
    #         param_list.append(value_i)
    #         selected_row_index.append(row_index)
    #     # END-IF
    #
    #     log_index_vec = np.array(selected_row_index) + 1
    #     param_vec = np.array(param_list)
    #
    #     return log_index_vec, param_vec


    def get_function_parameter_names(self):
        """
        get all the function parameters' names
        :return:
        """
        fitted_param_names = self._fitted_function_param_table.getColumnNames()
        fitted_param_names.append('center_d')

        return fitted_param_names

    def get_number_scans(self):
        """ Get number of scans in input data to fit
        :return:
        """
        data_workspace = self.retrieve_workspace(self._workspace_name, True)
        return data_workspace.getNumberHistograms()

    @staticmethod
    def retrieve_workspace(ws_name, throw_if_not_exist):
        """
        retrieve the workspace.
        optionally throw a runtime error if the workspace does not exist.
        :param ws_name:
        :param throw_if_not_exist:
        :return: workspace instance or None (if throw_if_not_exist is set to False)
        """
        # check inputs
        checkdatatypes.check_string_variable('Workspace name', ws_name)
        checkdatatypes.check_bool_variable('Throw exception if workspace does not exist', throw_if_not_exist)

        # get
        if AnalysisDataService.doesExist(ws_name):
            workspace = AnalysisDataService.retrieve(ws_name)
        elif throw_if_not_exist:
            raise RuntimeError('Workspace {0} does not exist in Mantid ADS'.format(throw_if_not_exist))
        else:
            workspace = None

        return workspace
