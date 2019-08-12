# This is the core of PyRS serving as the controller of PyRS and hub for all the data
from pyrs.utilities import checkdatatypes
from pyrs.core import instrument_geometry
# from pyrs.utilities import rs_scan_io
from pyrs.utilities import file_util
from pyrs.utilities import rs_project_file
from pyrs.core import mask_util
import mantid_fit_peak
import strain_stress_calculator
import reduction_manager
import polefigurecalculator
import os
import numpy

# Define Constants
SUPPORTED_PEAK_TYPES = ['PseudoVoigt', 'Gaussian', 'Voigt']  # 'Lorentzian': No a profile of HB2B


class PyRsCore(object):
    """
    PyRS core
    """
    def __init__(self):
        """
        initialization
        """
        # declaration of class members
        self._reduction_manager = reduction_manager.HB2BReductionManager()

        # working environment
        if os.path.exists('tests/testdata/'):
            self._working_dir = 'tests/testdata/'
        else:
            self._working_dir = os.getcwd()

        # These are for peak fitting and etc.
        # TODO - AFTER #72 - Better to refactor!
        self._last_optimizer = None  # None or RsPeakFitEngine/MantidPeakFitEngine instance

        # container for optimizers
        self._optimizer_dict = dict()

        # pole figure calculation
        self._pole_figure_calculator_dict = dict()
        self._last_pole_figure_calculator = None

        # strain and stress calculator
        self._ss_calculator_dict = dict()   # [session name][strain/stress type: 1/2/3] = ss calculator
        self._curr_ss_session = None
        self._curr_ss_type = None

        return

    def new_strain_stress_session(self, session_name, is_plane_stress, is_plane_strain):
        """ Create a new strain/stress session by initializing a new StrainStressCalculator instance
        :param session_name: name of strain/stress session to query
        :param is_plane_stress: flag for being plane stress (specific equation)
        :param is_plane_strain:
        :return:
        """
        ss_type = self._get_strain_stress_type_key(is_plane_strain, is_plane_stress)
        new_ss_calculator = strain_stress_calculator.StrainStressCalculator(session_name, is_plane_strain,
                                                                            is_plane_stress)

        self._ss_calculator_dict[session_name] = dict()
        self._ss_calculator_dict[session_name][ss_type] = new_ss_calculator
        self._curr_ss_session = session_name
        self._curr_ss_type = ss_type

        return

    @property
    def peak_fitting_controller(self):
        """
        return handler to peak fitting manager
        :return:
        """
        return self._peak_fitting_controller

    @property
    def current_data_reference_id(self):
        """
        get the current/latest data reference ID
        :return:
        """
        return self._curr_data_key

    @property
    def strain_stress_calculator(self):
        """
        return the handler to strain/stress calculator
        :return:
        """
        if self._curr_ss_session is None:
            return None

        return self._ss_calculator_dict[self._curr_ss_session][self._curr_ss_type]

    @property
    def working_dir(self):
        """
        get working directory
        :return:
        """
        return self._working_dir

    @working_dir.setter
    def working_dir(self, user_dir):
        """
        set working directory
        :param user_dir:
        :return:
        """
        checkdatatypes.check_file_name(user_dir, check_writable=False, is_dir=True)

        self._working_dir = user_dir

        return

    # TODO FIXME - NOW - Broken
    def calculate_pole_figure(self, data_key, detector_id_list):
        """ API method to calculate pole figure by a specified data key
        :param data_key:
        :param detector_id_list:
        :return:
        """
        # check input
        checkdatatypes.check_string_variable('Data key/ID', data_key)
        if detector_id_list is None:
            detector_id_list = self.get_detector_ids(data_key)
        else:
            checkdatatypes.check_list('Detector IDs', detector_id_list)

        # get peak intensities from fitting
        # peak_intensities = self.get_peak_intensities(data_key, detector_id_list)

        # initialize pole figure
        self._last_pole_figure_calculator = polefigurecalculator.PoleFigureCalculator()
        self._pole_figure_calculator_dict[data_key] = self._last_pole_figure_calculator

        # set up pole figure logs and get it
        log_names = [('2theta', '2theta'),
                     ('omega', 'omega'),
                     ('chi', 'chi'),
                     ('phi', 'phi')]

        for det_id in detector_id_list:
            # get intensity and log value
            log_values = self.data_center.get_scan_index_logs_values((data_key, det_id), log_names)

            try:
                optimizer = self._get_optimizer((data_key, det_id))
                peak_intensities = optimizer.get_peak_intensities()
            except AttributeError as att:
                raise RuntimeError('Unable to get peak intensities. Check whether peaks have been fit.  FYI: {}'
                                   ''.format(att))
            fit_info_dict = optimizer.get_peak_fit_parameters()

            # add value to pole figure calculate
            self._last_pole_figure_calculator.add_input_data_set(det_id, peak_intensities, fit_info_dict, log_values)
        # END-FOR

        # do calculation
        self._last_pole_figure_calculator.calculate_pole_figure(detector_id_list)

        return

    def get_pole_figure_values(self, data_key, detector_id_list, max_cost):
        """ API method to get the (N, 3) array for pole figures
        :param data_key:
        :param detector_id_list:
        :param max_cost:
        :return:
        """
        pole_figure_calculator = self._pole_figure_calculator_dict[data_key]
        assert isinstance(pole_figure_calculator, polefigurecalculator.PoleFigureCalculator),\
            'Pole figure calculator type mismatched. Input is of type {0} but expected as {1}.' \
            ''.format(type(pole_figure_calculator), 'polefigurecalculator.PoleFigureCalculato')

        if detector_id_list is None:
            detector_id_list = pole_figure_calculator.get_detector_ids()
        else:
            checkdatatypes.check_list('Detector ID list', detector_id_list)

        # get all the pole figure vectors
        vec_alpha = None
        vec_beta = None
        vec_intensity = None
        for det_id in detector_id_list:
            print ('[DB...BAt] Get pole figure from detector {0}'.format(det_id))
            # get_pole_figure returned 2 tuple.  we need the second one as an array for alpha, beta, intensity
            sub_array = pole_figure_calculator.get_pole_figure_vectors(det_id, max_cost)[1]
            vec_alpha_i = sub_array[:, 0]
            vec_beta_i = sub_array[:, 1]
            vec_intensity_i = sub_array[:, 2]

            print ('Det {} # data points = {}'.format(det_id, len(sub_array)))
            # print ('alpha: {0}'.format(vec_alpha_i))

            if vec_alpha is None:
                vec_alpha = vec_alpha_i
                vec_beta = vec_beta_i
                vec_intensity = vec_intensity_i
            else:
                vec_alpha = numpy.concatenate((vec_alpha, vec_alpha_i), axis=0)
                vec_beta = numpy.concatenate((vec_beta, vec_beta_i), axis=0)
                vec_intensity = numpy.concatenate((vec_intensity, vec_intensity_i), axis=0)
            # END-IF-ELSE
            print ('Updated alpha: size = {0}: {1}'.format(len(vec_alpha), vec_alpha))
        # END-FOR

        return vec_alpha, vec_beta, vec_intensity

    def get_pole_figure_value(self, data_key, detector_id, log_index):
        """
        get pole figure value of a certain measurement identified by data key and log index
        :param data_key:
        :param detector_id
        :param log_index:
        :return:
        """
        checkdatatypes.check_int_variable('Scan log #', log_index, (0, None))

        alpha, beta = self._last_pole_figure_calculator.get_pole_figure_1_pt(detector_id, log_index)

        # log_index_list, pole_figures = self._last_pole_figure_calculator.get_pole_figure_vectors(detector_id, max_cost=None)
        # if len(pole_figures) < log_index + 1:
        #     alpha = 0
        #     beta = 0
        # else:
        #     try:
        #         alpha = pole_figures[log_index][0]
        #         beta = pole_figures[log_index][1]
        #     except ValueError as val_err:
        #         raise RuntimeError('Given detector {0} scan log index {1} of data IDed as {2} is out of range as '
        #                            '({3}, {4})  (error = {5})'
        #                            ''.format(detector_id, log_index, data_key, 0, len(pole_figures), val_err))
        # # END-IF-ELSE

        return alpha, beta

    @staticmethod
    def _check_data_key(data_key_set):
        if isinstance(data_key_set, tuple) and len(data_key_set) == 2:
            data_key, sub_key = data_key_set
        elif isinstance(data_key_set, tuple):
            raise RuntimeError('Wrong!')
        else:
            data_key = data_key_set
            checkdatatypes.check_string_variable('Data reference ID', data_key)
            sub_key = None

        return data_key, sub_key

    def fit_peaks(self, session_name, sub_run_list, peak_type, background_type, fit_range):
        """
        Fit a single peak on each diffraction pattern selected from client-specified
        :param session_name:
        :param sub_run_list: None as the default as All;
        :param peak_type:
        :param background_type:
        :param fit_range:
        :return:
        """
        from pyrs.core import peak_fit_factory
        # Get workspace
        workspace = self.reduction_manager.get_hidra_workspace(session_name)

        # For the data for fitting
        self._peak_fit_controller = peak_fit_factory.PeakFitEngineFactory.getInstance('Mantid')(workspace, sub_run_list)

        # fit peaks
        self._peak_fit_controller.fit_peaks(peak_type, background_type, fit_range)

        return

    # TODO FIXME - NOW - Broken now
    def fit_peaks_old(self, data_key_set, scan_index, peak_type, background_type, fit_range):
        """
        fit a single peak of a measurement in a multiple-log scan
        :param data_key_set:
        :param scan_index:
        :param peak_type:
        :param background_type:
        :param fit_range
        :return: reference ID
        """
        # Check inputs
        if isinstance(data_key_set, tuple) and len(data_key_set) == 2:
            data_key, sub_key = data_key_set
        elif isinstance(data_key_set, tuple):
            raise RuntimeError('Wrong!')
        else:
            data_key = data_key_set
            checkdatatypes.check_string_variable('Data reference ID', data_key)
            sub_key = None

        checkdatatypes.check_string_variable('Peak type', peak_type)
        checkdatatypes.check_string_variable('Background type', background_type)

        # get scan indexes
        if scan_index is None:
            scan_index_list = self._data_manager.get_scan_range(data_key, sub_key)
        elif isinstance(scan_index, int):
            # check range
            scan_index_list = [scan_index]
        elif isinstance(scan_index, list):
            scan_index_list = scan_index
        else:
            raise RuntimeError('Scan index ({0}) is not supported.'.format(scan_index))

        # get data
        diff_data_list = list()
        # TODO - FUTURE - sun run will be used to replace log_index
        for log_index in scan_index_list:
            diff_data = self._data_manager.get_reduced_diffraction_data(data_key_set, log_index)
            diff_data_list.append(diff_data)
        # END-FOR

        if sub_key is None:
            ref_id = '{0}'.format(data_key)
        else:
            ref_id = '{0}_{1}'.format(data_key, sub_key)
        peak_optimizer = mantid_fit_peak.MantidPeakFitEngine(scan_index_list, diff_data_list, ref_id=ref_id)

        # observed COM and highest Y value data point
        print ('[DB...BAT] Fit Engine w/ Key: {0}'.format(data_key_set))
        peak_optimizer.calculate_center_of_mass()
        # fit peaks
        peak_optimizer.fit_peaks(peak_type, background_type, fit_range, None)

        # convert peak center to d-spacing
        if sub_key is None:
            wave_length_vec = self.data_center.get_sample_log_values(data_key, sample_log_name='Wavelength')
        else:
            # texture analysis case
            wave_length_vec = self.data_center.get_sample_log_values((data_key, sub_key), sample_log_name='Wavelength')
        peak_optimizer.calculate_peak_position_d(wave_length_vec=wave_length_vec)

        self._last_optimizer = peak_optimizer
        self._optimizer_dict[data_key_set] = self._last_optimizer

        return ref_id

    def _get_optimizer(self, data_key):
        """
        get optimizer.
        raise exception if optimizer to return is None
        :param data_key:
        :return:
        """
        # check input
        if self._last_optimizer is None:
            # never been used
            return None
        elif data_key is None and self._last_optimizer is not None:
            # by default: current optimizer
            print ('Return last optimizer')
            optimizer = self._last_optimizer
        elif data_key in self._optimizer_dict:
            # with data key
            optimizer = self._optimizer_dict[data_key]
            print ('Return optimizer in dictionary: {0}'.format(optimizer))
        else:
            # data key exist but optimizer does not: could be not been fitted yet
            raise RuntimeError('Unable to find optimizer related to data with reference ID {0} of type {1}.'
                               'Current keys are {2}.'
                               ''.format(data_key, type(data_key), self._optimizer_dict.keys()))

        return optimizer

    @staticmethod
    def _get_strain_stress_type_key(is_plane_strain, is_plane_stress):
        """
        blabla
        :param is_plane_strain:
        :param is_plane_stress:
        :return: 1: regular unconstrained, 2: plane strain, 3: plane stress
        """
        if is_plane_strain:
            return 2
        elif is_plane_stress:
            return 3

        return 1

    def get_detector_ids(self, data_key):
        """
        get detector IDs for the data loaded as h5 list
        :param data_key:
        :return:
        """
        self._check_data_key(data_key)

        return self._data_manager.get_sub_keys(data_key)

    def get_diffraction_data(self, session_name, sub_run, mask):
        """ get diffraction data of a certain session/wokspace
        :param session_name: name of session for workspace
        :param sub_run: sub run of the diffraction ata
        :param mask: String as mask ID for reduced diffraction data
        :return: tuple: vec_2theta, vec_intensit
        """
        diff_data_set = self._reduction_manager.get_reduced_diffraction_data(session_name, sub_run, mask)

        return diff_data_set

    def get_modeled_data(self, data_key, scan_log_index):
        """
        get calculated data according to fitted model
        :param data_key:
        :param scan_log_index:
        :return:
        """
        checkdatatypes.check_int_variable('Scan index', scan_log_index, (0, None))
        # get data key
        if data_key is None:
            data_key = self._curr_data_key
            if data_key is None:
                raise RuntimeError('There is no current loaded data.')
        # END-IF

        optimizer = self._get_optimizer(data_key)
        if optimizer is None:
            data_set = None
        else:
            data_set = optimizer.get_calculated_peak(scan_log_index)

        return data_set

    def get_peak_fit_parameter_names(self, data_key=None):
        """
        get the fitted function's parameters
        :param data_key:
        :return: list (of parameter names)
        """
        # check input
        optimizer = self._get_optimizer(data_key)
        if optimizer is None:
            return None

        return optimizer.get_function_parameter_names()

    # TODO - TONIGHT NOW - Need to migrate to new get_fitted_params
    def get_peak_fit_param_value(self, data_key, param_name_list, max_cost):
        """
        get a specific parameter's fitted value
        :param data_key:
        :param param_name:
        :param max_cost: if not None, then filter out the bad (with large cost) fitting
        :return: 1 vector or 2-tuple (vector + vector)
        """
        # check input
        optimizer = self._get_optimizer(data_key)

        if max_cost is None:
            sub_run_vec, param_vec = optimizer.get_fitted_params(param_name_list, False)
            log_index_vec = numpy.arange(len(param_vec))
        else:
            log_index_vec, param_vec = optimizer.get_good_fitted_params(param_name, max_cost)

        return sub_run_vec, param_vec

    def get_peak_fit_param_value_error(self, data_key, param_name, max_cost):
        """ Get a specific peak parameter's fitting value with error
        :param data_key:
        :param param_name:
        :param max_cost:
        :return: 2-tuple: (1) (n, ) for sub runs (2) array as (n, 2) such that [i, 0] is value and [i, 1] is error
        """
        # check input
        fit_engine = self._get_optimizer(data_key)

        if max_cost is None:
            sub_run_vec, param_error_vec = fit_engine.get_fitted_params(param_name,  inlcuding_error=True)
        else:
            sub_run_vec, param_error_vec = fit_engine.get_good_fitted_params(param_name, max_cost, inlcuding_error=True)

        return sub_run_vec, param_error_vec

    # TODO FIXME - TONIGHT NOW - This method shall be migrated to newer API to get parameter values
    def get_peak_fit_params_in_dict(self, data_key):
        """
        export the complete set of peak parameters fitted to a dictionary
        :param data_key:
        :return:
        """
        # check input
        optimizer = self._get_optimizer(data_key)

        # get names, detector IDs (for check) & log indexes
        param_names = optimizer.get_function_parameter_names()
        detector_ids = self.get_detector_ids(data_key)
        print ('[DB...BAT] Detector IDs = {}'.format(detector_ids))
        if detector_ids is not None:
            raise NotImplementedError('Multiple-detector ID case has not been considered yet. '
                                      'Contact developer for this issue.')
        scan_log_index_list = optimizer.get_scan_indexes()

        # init dictionary
        fit_param_value_dict = dict()
        for scan_log_index in scan_log_index_list:
            param_dict = dict()
            fit_param_value_dict[scan_log_index] = param_dict
        # END-FOR

        for param_name in param_names:
            scan_index_vec, param_value = self.get_peak_fit_param_value(data_key, [param_name], max_cost=None)
            checkdatatypes.check_numpy_arrays('Parameter values', [param_value], dimension=1, check_same_shape=False)
            # add the values to dictionary
            for si in range(len(scan_index_vec)):
                scan_log_index = scan_index_vec[si]
                if scan_log_index not in fit_param_value_dict:
                    fit_param_value_dict[scan_log_index] = dict()
                fit_param_value_dict[scan_log_index][param_name] = param_value[scan_log_index]
            # END-FOR (scan-log-index)
        # END-FOR (param_name)

        return fit_param_value_dict

    def get_peak_fit_scan_log_indexes(self, data_key):
        """
        get the scan log indexes from an optimizer
        :param data_key:
        :return: list of integers
        """
        # check input
        optimizer = self._get_optimizer(data_key)

        return optimizer.get_scan_indexes()

    def get_peak_center_of_mass(self, data_key):
        """
        get 'observed' center of mass of a peak
        :param data_key:
        :return:
        """
        optimizer = self._get_optimizer(data_key)

        return optimizer.get_observed_peaks_centers()[:, 0]

    def get_peak_intensities(self, data_key_pair):
        """
        get the peak intensities
        :param data_key_pair:
        :return: a dictionary (key = detector ID) of dictionary (key = scan index, value = peak intensity)
        """
        optimizer = self._get_optimizer(data_key_pair)
        peak_intensities = optimizer.get_peak_intensities()

        return peak_intensities

    def load_hidra_project(self, hidra_h5_name, project_name, load_detector_counts=True, load_diffraction=False):
        """
        Load a HIDRA project file
        :param hidra_h5_name: name of HIDRA project file in HDF5 format
        :param project_name: name of the reduction project specified by user to trace
        :param load_detector_counts:
        :param load_diffraction:
        :return:
        """
        # Initialize session
        self._reduction_manager.init_session(project_name)

        # Load project
        self._reduction_manager.load_hidra_project(hidra_h5_name, False, load_detector_counts, load_diffraction)

        return

    def save_diffraction_data(self, project_name, file_name):
        """

        :param project_name:
        :param file_name:
        :return:
        """
        self.reduction_manager.save_reduced_diffraction(project_name, file_name)

        return

    def save_peak_fit_result(self, data_key, src_rs_file_name, target_rs_file_name):
        """ Save peak fit result to file with original data
        :param data_key:
        :param src_rs_file_name:
        :param target_rs_file_name:
        :return:
        """
        peak_fit_dict = self.get_peak_fit_params_in_dict(data_key)
        self._file_io_controller.export_peak_fit(src_rs_file_name, target_rs_file_name,
                                                 peak_fit_dict)

        return

    def save_pole_figure(self, data_key, detectors, file_name, file_type):
        """
        save pole figure/export pole figure
        :param data_key:
        :param detectors: a list of detector (ID)s or None (default for all detectors)
        :param file_name:
        :param file_type:
        :return:
        """
        checkdatatypes.check_string_variable('Data key', data_key)

        if data_key in self._pole_figure_calculator_dict:
            self._pole_figure_calculator_dict[data_key].export_pole_figure(detectors, file_name, file_type)
        else:
            raise RuntimeError('Data key {0} is not calculated for pole figure.  Current data keys contain {1}'
                               ''.format(data_key, self._pole_figure_calculator_dict.keys()))

        return

    def reduce_diffraction_data(self, session_name, two_theta_step, pyrs_engine, mask_file_name=None,
                                geometry_calibration=None):
        """ Reduce all sub runs in a workspace from detector counts to diffraction data
        :param session_name:
        :param two_theta_step:
        :param pyrs_engine:
        :param mask_file_name:
        :param geometry_calibration: True/file name/AnglerCameraDetectorShift/None), False, None/(False, )
        :return:
        """
        # Mask file
        if mask_file_name:
            mask_info = self._reduction_manager.load_mask_file(mask_file_name)
            mask_id = mask_info[2]
            print ('L650 Mask ID = {}'.format(mask_id))
        else:
            mask_id = None

        # Geometry calibration
        if geometry_calibration is None or geometry_calibration is False:
            # No apply
            apply_calibration = False
        elif isinstance(geometry_calibration, str):
            # From a Json file
            calib_shift = instrument_geometry.AnglerCameraDetectorShift(0, 0, 0, 0, 0, 0)
            calib_shift.from_json(geometry_calibration)
            apply_calibration = calib_shift
        elif isinstance(geometry_calibration, instrument_geometry.AnglerCameraDetectorShift):
            # Already a AnglerCameraDetectorShift instance
            apply_calibration = geometry_calibration
        elif geometry_calibration is True:
            # Use what is loaded from file or set to workspace before
            apply_calibration = True
        else:
            raise RuntimeError('Argument geometry_calibration of value {} and type {} is not supported'
                               ''.format(geometry_calibration, type(geometry_calibration)))
        # END-IF-ELSE

        self._reduction_manager.reduce_diffraction_data(session_name, apply_calibration,
                                                        two_theta_step, pyrs_engine,
                                                        mask_id)

        return

    @property
    def reduction_manager(self):
        """
        get the reference to reduction engine
        :return:
        """
        return self._reduction_manager

    def reset_strain_stress(self, is_plane_strain, is_plane_stress):
        """ reset the strain and stress calculation due to change of type

        :param is_plane_strain:
        :param is_plane_stress:
        :return:
        """
        if self._curr_ss_session is None:
            raise RuntimeError('Current session is not named.')
        elif self._curr_ss_session not in self._ss_calculator_dict:
            print ('[WARNING] Current strain/stress session does not exist.')
            return

        ss_type_index = self._get_strain_stress_type_key(is_plane_strain, is_plane_stress)
        if ss_type_index == self._curr_ss_type:
            raise RuntimeError('Same strain/stress type (plane strain = {}, plane stress = {}'
                               ''.format(is_plane_strain, is_plane_stress))

        # rename the current strain stress name
        # saved_ss_name = self._curr_ss_session + '_{}_{}'.format(is_plane_strain, is_plane_stress)
        # self._ss_calculator_dict[self._curr_ss_session].rename(saved_ss_name)
        # prev_calculator = self._ss_calculator_dict[self._curr_ss_session]
        # self._ss_calculator_dict[saved_ss_name] = prev_calculator

        # reset new strain/stress calculator
        new_ss_calculator = self.strain_stress_calculator.migrate(is_plane_strain, is_plane_stress)

        self._ss_calculator_dict[self._curr_ss_session][ss_type_index] = new_ss_calculator
        self._curr_ss_type = ss_type_index

        return self._curr_ss_session

    def save_nexus(self, data_key, file_name):
        """
        save data in a MatrixWorkspace to Mantid processed NeXus file
        :param data_key:
        :param file_name:
        :return:
        """
        # Check
        optimizer = self._get_optimizer(data_key)

        # get the workspace name
        try:
            matrix_name = optimizer.get_data_workspace_name()
            # save
            file_util.save_mantid_nexus(matrix_name, file_name)
        except RuntimeError as run_err:
            raise RuntimeError('Unable to write to NeXus because Mantid fit engine is not used.\nError info: {0}'
                               ''.format(run_err))

        try:
            matrix_name = optimizer.get_center_of_mass_workspace_name()
            # save
            dir_name = os.path.dirname(file_name)
            base_name = os.path.basename(file_name)
            file_name = os.path.join(dir_name, base_name.split('.')[0] + '_com.nxs')
            file_util.save_mantid_nexus(matrix_name, file_name)
        except RuntimeError as run_err:
            raise RuntimeError('Unable to write COM to NeXus because Mantid fit engine is not used.\nError info: {0}'
                               ''.format(run_err))

        return

    @property
    def supported_peak_types(self):
        """
        list of supported peaks' types for fitting
        :return:
        """
        return SUPPORTED_PEAK_TYPES[:]
