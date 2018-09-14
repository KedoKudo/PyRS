try:
    from PyQt5.QtWidgets import QDialog, QMainWindow
    from PyQt5.QtCore import pyqtSignal
except ImportError:
    from PyQt4.QtGui import QDialog, QMainWindow
    from PyQt4.QtCore import pyqtSignal

import gui_helper
from pyrs.utilities import checkdatatypes
from ui import ui_newsessiondialog
from ui import ui_strainstressgridsetup
from ui import ui_strainstressview
import ui.ui_gridsalignmentview
import ui.ui_sliceexportdialog


class CreateNewSessionDialog(QDialog):
    """ Create a new strain/stress session dialog
    """
    NewSessionSignal = pyqtSignal(str, bool, bool, name='new session signal')

    def __init__(self, parent):
        """
        initialization
        :param parent:
        """
        super(CreateNewSessionDialog, self).__init__(parent)

        self.ui = ui_newsessiondialog.Ui_Dialog()
        self.ui.setupUi(self)

        self.ui.buttonBox.accepted.connect(self.do_new_session)
        self.ui.buttonBox.rejected.connect(self.do_quit)

        # connect the signal
        self.NewSessionSignal.connect(parent.new_strain_stress_session)

        # init widgets
        self.ui.comboBox_strainStressType.clear()
        self.ui.comboBox_strainStressType.addItem('Unconstrained Strain/Stress')
        self.ui.comboBox_strainStressType.addItem('Plane Strain')
        self.ui.comboBox_strainStressType.addItem('Plane Stress')

        return

    def do_new_session(self):
        """
        new session
        :return:
        """
        session_name = str(self.ui.lineEdit_sessionName.text()).strip()
        if len(session_name) == 0:
            gui_helper.pop_message(self, 'Session name must be specified', 'error')
            return

        ss_type = self.ui.comboBox_strainStressType.currentIndex()
        is_plane_stress = False
        is_plane_strain = False

        if ss_type == 1:
            is_plane_strain = True
        elif ss_type == 2:
            is_plane_stress = True

        # send signal
        self.NewSessionSignal.emit(session_name, is_plane_strain, is_plane_stress)

        # quit eventually
        self.do_quit()

        return

    def do_quit(self):

        self.close()

    def reset_dialog(self):
        """
        reset the dialog input from last use
        :return:
        """
        self.ui.lineEdit_sessionName.setText('')

        return


class ExportGridSliceSetupDialog(QDialog):
    """
    Set up slicing (coordinate) direction and value
    Example: Y = 0 +/- 0.01
    """
    def __init__(self, parent):
        """
        initialization
        :param parent:
        """
        super(ExportGridSliceSetupDialog, self).__init__(parent)

        # setup ui
        self.ui = ui.ui_sliceexportdialog.Ui_Dialog()
        self.ui.setupUi(self)

        # set default value
        self.ui.lineEdit_resolution.setText('0.001')

        return

    def get_slicing_setup(self):
        """ get slicing set up
        Note: integer slicing direction: x <--> 0, y <--> 1, z <--> 2
        :return: 3-tuple: direction (int), value (float), resolution (float)
        """
        slice_dir = self.ui.comboBox_coordDir.currentIndex()

        try:
            slice_value = float(self.ui.lineEdit_value.text())
            resolution = float(self.ui.lineEdit_resolution.text())
        except ValueError as value_err:
            raise RuntimeError('Unable to parse position to slice at')

        return slice_dir, slice_value, resolution
# END-DEF-CLASS


class GridAlignmentCheckTablesView(QMainWindow):
    """ A set of tables in order to check grid alignment in order to set up the final grids
    """
    def __init__(self, parent):
        """ Initialization
        :param parent:
        """
        super(GridAlignmentCheckTablesView, self).__init__(parent)

        # define my parent
        self._parent = parent
        self._core = parent.core

        # state
        self._is_analysis_table_raw = True   # analysis table has raw experiment grids

        self.ui = ui.ui_gridsalignmentview.Ui_MainWindow()
        self.ui.setupUi(self)

        # init widgets
        self.ui.pushButton_showParameterSSGrid.setEnabled(False)

        # define events handlers
        self.ui.actionQuit.triggered.connect(self.do_quit)
        self.ui.pushButton_showParameterRawGrid.clicked.connect(self.do_load_params_raw_grid)
        self.ui.pushButton_showParameterSSGrid.clicked.connect(self.do_load_mapped_values)
        self.ui.pushButton_plot2D.clicked.connect(self.do_plot_parameter)
        self.ui.pushButton_export2D.clicked.connect(self.do_export_2d)

        # combo box event handling and mutex
        self.ui.comboBox_parameterList.currentIndexChanged.connect(self.do_show_parameter)
        self._mutex_param_name_list = False

        # set up all the tables
        self.ui.tableView_gridAlignment.setup()
        self.ui.tableView_gridStatistic.setup()
        self.ui.tableView_alignedParameters.setup()
        self.ui.tableView_matchedGrids.setup()
        self.ui.tableView_partialMatchedGrids.setup()
        self.ui.tableView_mismatchedGrids.setup()
        self.ui.tableView_gridParamAnalysis.setup()

        return

    def do_export_2d(self):
        """
        export a plane (2D) in the 3D grid system
        :return:
        """
        setup_tuple = get_grid_slicing_export_setup(self)
        if setup_tuple is None:
            return
        else:
            slice_dir, slice_pos, slice_resolution = setup_tuple

        file_name = gui_helper.browse_file(self, caption='Export a slice of the grids',
                                           default_dir=self._core.working_dir,
                                           file_filter='HDF (*.hdf5)',
                                           save_file=True)

        # save file
        param_name = str(self.ui.comboBox_parameterNamesAnalysis.currentText())
        ss_dir = str(self.ui.comboBox_ssDirection.currentText())
        self._core.strain_stress_calculator.export_2d_slice(param_name, self._is_analysis_table_raw, ss_dir, slice_dir,
                                                            slice_pos, slice_resolution, file_name)

        return

    def do_load_mapped_values(self):
        """
        show the mapped values of a parameter to user defined grids on a certain direction
        :return:
        """
        # get parameter name and direction
        param_name = str(self.ui.comboBox_parameterNamesAnalysis.currentText())
        ss_dir = str(self.ui.comboBox_ssDirection.currentText())

        # get value: returned list spec can be found in both rctables and strain stress calculator
        aligned_grid_param_values = self._core.strain_stress_calculator.get_user_grid_param_values(ss_dir, param_name)
        output_grid_vec = self._core.strain_stress_calculator.get_strain_stress_grid()

        # set value
        self.ui.tableView_gridParamAnalysis.reset_table()

        # print ('[DB...BAT] Parameter {} @ {} on raw grid:\n{}'.format(param_name, ss_dir, aligned_grid_param_values))
        self.ui.tableView_gridParamAnalysis.set_user_grid_parameter_values(output_grid_vec, aligned_grid_param_values,
                                                                           ss_dir)

        # disable 'load raw' and enable 'map output'
        self.ui.pushButton_showParameterRawGrid.setEnabled(True)
        self.ui.pushButton_showParameterSSGrid.setEnabled(False)

        return

    def do_load_params_raw_grid(self):
        """
        load parameter values on raw grid
        :return:
        """
        # get parameter name and direction
        param_name = str(self.ui.comboBox_parameterNamesAnalysis.currentText())
        print ('[DB...BAT] parameter index : {}'.format(self.ui.comboBox_parameterNamesAnalysis.currentIndex()))
        ss_dir = str(self.ui.comboBox_ssDirection.currentText())

        # get value: returned list spec can be found in both rctables and strain stress calculator
        raw_grid_param_values = self._core.strain_stress_calculator.get_raw_grid_param_values(ss_dir, param_name)

        # set value
        self.ui.tableView_gridParamAnalysis.reset_table()
        self.ui.tableView_gridParamAnalysis.set_raw_grid_parameter_values(raw_grid_param_values)

        # disable 'load raw' and enable 'map output'
        self.ui.pushButton_showParameterRawGrid.setEnabled(False)
        self.ui.pushButton_showParameterSSGrid.setEnabled(True)

        return

    def do_plot_parameter(self):
        """

        :return:
        """
        param_name = str(self.ui.comboBox_parameterNamesAnalysis.currentText())
        ss_dir = str(self.ui.comboBox_ssDirection.currentText())

        # if shift to raw is disabled, then it means that it is in RAW state
        if self.ui.pushButton_showParameterRawGrid.isEnabled():
            plot_raw = False
        else:
            plot_raw = True

        self._parent.plot_peak_param_slice(param_name=param_name, ss_direction=ss_dir, is_raw_grid=plot_raw)

        return

    def do_quit(self):
        """ close the window
        :return:
        """
        self.close()

        return

    def do_show_parameter(self):
        """ show the selected parameter's values on output grids (view only tab)
        :return:
        """
        if self._mutex_param_name_list:
            return

        # reset the table and add all the grids' value
        self.ui.tableView_gridAlignment.remove_all_rows()

        param_name = str(self.ui.comboBox_parameterList.currentText())
        for ss_dir in self._core.strain_stress_calculator.get_strain_stress_direction():
            user_grid_value_vec = \
                self._core.strain_stress_calculator.get_user_grid_param_values(ss_direction=ss_dir,
                                                                               param_name=param_name)
            self.ui.tableView_gridAlignment.set_grids_values(self._core.strain_stress_calculator.get_strain_stress_grid(),
                                                             {'e11': user_grid_value_vec})
            break

        return

    def reset_tables(self):
        """ reset all the tables
        :return:
        """
        self.ui.tableView_gridAlignment.remove_all_rows()
        self.ui.tableView_gridParamAnalysis.remove_all_rows()
        self.ui.tableView_alignedParameters.remove_all_rows()
        self.ui.tableView_matchedGrids.remove_all_rows()
        self.ui.tableView_mismatchedGrids.remove_all_rows()
        self.ui.tableView_partialMatchedGrids.remove_all_rows()

        return

    def set_aligned_grids_info(self, grid_array, mapping_array):
        """ set the aligned grid information to tableView_gridAlignment
        :param grid_array:
        :param mapping_array:
        :return:
        """
        assert grid_array.shape[0] == mapping_array.shape[0], 'blabla'

        num_rows = grid_array.shape[0]
        num_ss_dir = mapping_array.shape[1]

        # clear the table
        self.ui.tableView_gridAlignment.remove_all_rows()

        for i in range(num_rows):
            pos_x, pos_y, pos_z = grid_array[i]
            e11_scan_index = mapping_array[i][0]
            e22_scan_index = mapping_array[i][1]
            if num_ss_dir == 3:
                e33_scan_index = mapping_array[i][2]
            else:
                e33_scan_index = None

            self.ui.tableView_gridAlignment.add_grid(pos_x, pos_y, pos_z, e11_scan_index, e22_scan_index,
                                                     e33_scan_index)
        # END-FOR (i)

        return

    def set_aligned_parameter_value(self, param_name, param_value_vector):
        """
        set the aligned parameter values to Table...
        :param param_name:
        :param param_value_vector:
        :return:
        """
        print ('[DB...BAT] Set {}  Value vector shape = {}'.format(param_name, param_value_vector.shape))

        for i_row in range(param_value_vector.shape[0]):
            row_items = [1, 2, 3]
            for i_ss_dir in range(param_value_vector.shape[1]):
                row_items.append(param_value_vector[i_row, i_ss_dir])
            self.ui.tableView_alignedParameters.append_row(row_items)
        # END-FOR

        return

    def set_peak_parameter_names(self, peak_param_names):
        """ set the peak parameter names to combo box for user to specify
        :param peak_param_names:
        :return:
        """
        checkdatatypes.check_list('Peak parameter names', peak_param_names)

        # lock
        self._mutex_param_name_list = True

        # write
        self.ui.comboBox_parameterList.clear()
        self.ui.comboBox_parameterNamesAnalysis.clear()
        peak_param_names.sort()
        for p_name in peak_param_names:
            self.ui.comboBox_parameterList.addItem(p_name)
            self.ui.comboBox_parameterNamesAnalysis.addItem(p_name)
        # END-FOR

        # unlock
        self._mutex_param_name_list = False

        return

# END-DEF-CLASS ()


class StrainStressGridSetup(QDialog):
    """ Strain and stress calculation grids setup dialog
    """
    def __init__(self, parent):
        """ initialization
        :param parent:
        """
        super(StrainStressGridSetup, self).__init__(parent)

        self.ui = ui_strainstressgridsetup.Ui_Dialog()
        self.ui.setupUi(self)

        self.ui.buttonBox.accepted.connect(self.do_accept_user_input)

        self._is_user_specified_grids = False

        # for return
        self._grid_setup_dict = dict()

        # flag that user input is OK
        self._is_user_input_acceptable = True

        return

    def do_accept_user_input(self):
        """ pay attention for extra check up for user-specified grids
        :return:
        """
        try:
            self._parse_user_input(allow_empty=not self._is_user_specified_grids)
        except RuntimeError as run_err:
            gui_helper.pop_message(self,
                                   'User specified grids requiring all values to be input: {}'.format(run_err),
                                   'error')
            self._is_user_input_acceptable = False

        except ValueError as value_err:
            gui_helper.pop_message(self, 'User specified value incorrect: {}'.format(value_err),
                                   'error')
            self._is_user_input_acceptable = False

        # this will be called anyway to close the dialog
        super(StrainStressGridSetup, self).accept()

        return

    def _parse_user_input(self, allow_empty):
        """
        get the user inputs
        Example: lineEdit_gridMinX
        :return: as a dictionary
        """
        checkdatatypes.check_bool_variable('Flag to allow empty input', allow_empty)

        self._grid_setup_dict = dict()
        err_msg = ''
        for param_name in ['Min', 'Max', 'Resolution']:
            self._grid_setup_dict[param_name] = dict()
            for coord_i in ['X', 'Y', 'Z']:
                self._grid_setup_dict[param_name][coord_i] = None

                line_edit_name = 'lineEdit_grid{}{}'.format(param_name, coord_i)
                line_edit = getattr(self.ui, line_edit_name)
                value_str = str(line_edit.text()).strip()
                if value_str == '' and not allow_empty:
                    err_msg += '{} {} is empty\n'.format(param_name, coord_i)
                elif value_str != '':
                    value_i = float(value_str)
                    self._grid_setup_dict[param_name][coord_i] = value_i
            # END-FOR (coord_i)
        # END-FOR (param_name)

        if len(err_msg) > 0:
            raise RuntimeError(err_msg)

        return

    def get_grid_setup(self):
        """
        get setup
        :return:
        """
        return self._grid_setup_dict

    @property
    def is_input_acceptable(self):
        """
        whether the input is acceptable
        :return:
        """
        return self._is_user_input_acceptable

    def set_previous_inputs(self, grid_setup_dict):
        """
        set the previous user inputs of grid setup
        :param grid_setup_dict:
        :return:
        """
        # doing nothing
        if grid_setup_dict is None:
            return

        checkdatatypes.check_dict('Grid setup', grid_setup_dict)

        for param_name in ['Min', 'Max', 'Resolution']:
            for coord_i in ['X', 'Y', 'Z']:
                # do not set up if there is no user input
                if grid_setup_dict[param_name][coord_i] is None:
                    continue

                # set value
                line_edit_name = 'lineEdit_grid{}{}'.format(param_name, coord_i)
                line_edit = getattr(self.ui, line_edit_name)
                line_edit.setText('{}'.format(grid_setup_dict[param_name][coord_i]))
            # END-FOR
        # END-FOR

        return

    def set_user_grids_flag(self, state=True):
        """
        set the status to be user specified grids or not
        :param state: 
        :return: 
        """
        checkdatatypes.check_bool_variable('Flag for user specified grid', state)
        self._is_user_specified_grids = state

        return

    def set_experimental_data_statistics(self, stat_dict):
        """
        set the statistics data for the experiments
        [requirement] statistics dictionary
        level 1: type: min, max, num_indv_values
          level 2: direction: e11, e22(, e33)
            level 3: coordinate_dir: x, y, z
        :param stat_dict:
        :return:
        """
        checkdatatypes.check_dict('Grids statistics', stat_dict)

        # set up the minimum values, maximum values and number of individual values
        for dir_i in stat_dict['min'].keys():
            for coord_i in ['X', 'Y', 'Z']:
                line_edit_name = 'lineEdit_{}{}Min'.format(dir_i, coord_i)
                line_edit = getattr(self.ui, line_edit_name)
                print (stat_dict['min'][dir_i])
                line_edit.setText('{}'.format(stat_dict['min'][dir_i][coord_i]))
            # END-FOR
        # END-FOR

        # set up the maximum values
        for dir_i in stat_dict['max'].keys():
            for coord_i in ['X', 'Y', 'Z']:
                line_edit_name = 'lineEdit_{}{}Max'.format(dir_i, coord_i)
                line_edit = getattr(self.ui, line_edit_name)
                line_edit.setText('{}'.format(stat_dict['max'][dir_i][coord_i]))
            # END-FOR
        # END-FOR

        # set up the number of individual values
        for dir_i in stat_dict['num_indv_values'].keys():
            for coord_i in ['X', 'Y', 'Z']:
                line_edit_name = 'lineEdit_{}NumIndvPoints{}'.format(dir_i, coord_i)
                line_edit = getattr(self.ui, line_edit_name)
                line_edit.setText('{}'.format(stat_dict['num_indv_values'][dir_i][coord_i]))
            # END-FOR
        # END-FOR

        return


# END-DEFINE-CLASS


class StrainStressTableView(QMainWindow):
    """ A window to show the table of calculated strain and stress
    """
    def __init__(self, parent):
        """
        initialization
        :param parent:
        """
        super(StrainStressTableView, self).__init__(parent)

        # set up UI
        self.ui = ui_strainstressview.Ui_MainWindow()
        self.ui.setupUi(self)

        # init widgets
        self.ui.tableView_strainStressTable.setup()

        # define event handling
        self.ui.pushButton_close.clicked.connect(self.do_quit)

        return

    def do_quit(self):
        """
        quit
        :return:
        """
        self.close()

        return

    def reset_main_table(self):
        """
        reset the main strain/stress value table
        :return:
        """
        self.ui.tableView_strainStressTable.remove_all_rows()

        return

    def set_strain_stress_values(self, grid_vector, strain_vector, stress_vector):
        """ set strain and stress values.  Each row shall be a sample grid
        :param strain_stress_value_dict: key = grid position (vector) value = dict [strain, stress]
        :return:
        """
        # TODO - 20180905 - check input
        #

        num_grids = grid_vector.shape[0]

        for i_grid in range(num_grids):
            # get grid, strain and stress
            grid_vec = grid_vector[i_grid]
            strain_matrix = strain_vector[i_grid]
            stress_matrix = stress_vector[i_grid]

            # get the elements needed

            self.ui.tableView_strainStressTable.add_grid_strain_stress(grid_pos=grid_vec,
                                                                       strain_matrix=strain_matrix,
                                                                       stress_matrix=stress_matrix)
        # END-FOR

        return


def get_grid_slicing_export_setup(parent):
    """
    for exporting a slice on grid. get the setup such that on which axis which value to be sliced at and exported
    :param parent:
    :return:
    """
    # value to return
    return_value = None

    while True:
        # init
        slice_setup_dialog = ExportGridSliceSetupDialog(parent)

        # launch
        result = slice_setup_dialog.exec_()

        # process result
        if result:
            try:
                return_value = slice_setup_dialog.get_slicing_setup()
                break
            except RuntimeError as run_err:
                gui_helper.pop_message(parent, str(run_err), message_type='error')
        else:
            break
    # END-WHILE

    return return_value


def get_strain_stress_grid_setup(parent, user_define_grid, grid_stat_dict):
    """

    :return:
    """
    # set up dialog
    grid_setup_dict = None

    while True:
        ss_dialog = StrainStressGridSetup(parent)
        ss_dialog.set_experimental_data_statistics(grid_stat_dict)
        ss_dialog.set_user_grids_flag(user_define_grid)
        ss_dialog.set_previous_inputs(grid_setup_dict)

        # launch dialog and wait for result
        result = ss_dialog.exec_()

        # process result
        if not result:
            grid_setup_dict = None
            break
        else:
            # loop will be terminated if user cancels or user gives a good result
            grid_setup_dict = ss_dialog.get_grid_setup()
            if ss_dialog.is_input_acceptable:
                break

    return grid_setup_dict
