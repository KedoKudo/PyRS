try:
    from PyQt5.QtWidgets import QMainWindow, QFileDialog
except ImportError:
    from PyQt4.QtGui import QMainWindow, QFileDialog
import ui.ui_sscalvizwindow
from pyrs.utilities import checkdatatypes
import pyrs.core.pyrscore
import os
import gui_helper
import numpy
import platform
import ui.ui_sscalvizwindow


class StrainStressCalculationWindow(QMainWindow):
    """
    GUI window to calculate strain and stress with simple visualization
    """
    def __init__(self, parent):
        """
        initialization
        :param parent:
        """
        super(StrainStressCalculationWindow, self).__init__(parent)

        # class variables
        self._core = None

        # set up UI
        self.ui = ui.ui_sscalvizwindow.Ui_MainWindow()
        self.ui.setupUi(self)
        self._init_widgets()

        # set up event handling
        self.ui.pushButton_browseReducedFile.clicked.connect(self.do_browse_reduced_file)
        self.ui.pushButton_browse_e11ScanFile.clicked.connect(self.do_browse_e11_file)
        self.ui.pushButton_browse_e22ScanFile.clicked.connect(self.do_browse_e22_file)
        self.ui.pushButton_browse_e33ScanFile.clicked.connect(self.do_browse_e33_file)

        self.ui.pushButton_loadFile.clicked.connect(self.do_load_strain_file)
        self.ui.pushButton_calUnconstrainedStress.clicked.connect(self.do_cal_strain)
        self.ui.pushButton_calPlaneStress.clicked.connect(self.do_cal_stress)
        self.ui.pushButton_calPlaneStrain.clicked.connect(self.do_cal_stress)

        # strain/stress save and export
        self.ui.pushButton_saveStressStrain.clicked.connect(self.save_stress_strain)
        self.ui.pushButton_exportSpecialType.clicked.connect(self.export_stress_strain)

        # radio buttons changed case
        self.ui.radioButton_loadRaw.toggled.connect(self.evt_load_file_type)
        self.ui.radioButton_loadReduced.toggled.connect(self.evt_load_file_type)

        # combo boxes handling
        self.ui.comboBox_plotParameterName.currentIndexChanged.connect(self.do_plot_sliced_3d)

        # self.lineEdit_tdScanFile..connect(self.)
        # self.lineEdit_ndScanFile..connect(self.)
        # self.lineEdit_rdScanFile..connect(self.)
        #
        # self.lineEdit_reducedFile..connect(self.)
        #
        # self.lineEdit_outputFileName..connect(self.)
        # self.lineEdit_exportFileName..connect(self.)
        # self.plainTextEdit_info..connect(self.)
        # self.graphicsView_sliceView..connect(self.)
        # self.lineEdit_sliceStartValue..connect(self.)
        # self.lineEdit_sliceEndValue..connect(self.)
        # self.horizontalSlider_slicer..connect(self.)

        # current data/states
        self._core = None
        self._curr_data_key = None

        # mutex
        self._load_file_radio_mutex = False

        return

    def _init_widgets(self):
        """
        initialize widgets
        :return:
        """
        self.ui.radioButton_loadRaw.setChecked(False)
        self.ui.radioButton_loadReduced.setChecked(True)

        # set up label with Greek
        self.ui.label_poisson.setText(u'\u03BD (Poisson\' Ratio)')

        return

    def do_browse_e11_file(self):
        """ browse LD raw file
        :return:
        """
        ld_file_name = gui_helper.browse_file(self, caption='Load LD (raw) File',
                                              default_dir=self._core.working_dir,
                                              file_filter='Data File (*.dat)',
                                              file_list=False,
                                              save_file=False)
        if ld_file_name is not None:
            self.ui.lineEdit_e11ScanFile.setText(ld_file_name)

        return

    def do_browse_e22_file(self):
        """ browse ND raw file
        :return:
        """
        nd_file_name = gui_helper.browse_file(self, caption='Load ND (raw) File',
                                              default_dir=self._core.working_dir,
                                              file_filter='Data File (*.dat)',
                                              file_list=False,
                                              save_file=False)
        if nd_file_name is not None:
            self.ui.lineEdit_e22ScanFile.setText(nd_file_name)

        return

    def do_browse_e33_file(self):
        """ browse TD raw file
        :return:
        """
        td_file_name = gui_helper.browse_file(self, caption='Load TD (raw) File',
                                              default_dir=self._core.working_dir,
                                              file_filter='Data File (*.dat)',
                                              file_list=False,
                                              save_file=False)
        if td_file_name is not None:
            self.ui.lineEdit_e33ScanFile.setText(td_file_name)

        return

    def do_browse_reduced_file(self):
        """ browse the previous calculated and saved strain/stress file
        :return:
        """
        reduced_file_name = gui_helper.browse_file(self, caption='Previously saved stress/strain File',
                                                   default_dir=self._core.default_dir,
                                                   file_filter='Data File (*.dat);;HDF File (*.hdf)',
                                                   file_list=False,
                                                   save_file=False)

        if reduced_file_name is not None:
            self.ui.lineEdit_reducedFile.setText(reduced_file_name)

        return

    def do_cal_strain(self):
        """
        calculate strain from loaded file
        :return:
        """
        # TODO

        return

    def do_cal_stress(self):
        """
        calculate the stress from loaded file
        :return:
        """
        # TODO - Implement

        return

    def do_load_strain_file(self):
        """
        load strain/stress file from either raw files or previously saved file
        :return:
        """
        # current session is not canceled: ask user whether it is OK to delete and start a new one
        if self._curr_data_key is not None:
            continue_load = gui_helper.get_user_permit(caption='Current session shall be closed '
                                                               'before new session is started.', )
            if continue_load is False:
                return

        # get new session name
        session_name = gui_helper.get_session_dialog_name()

        if self.ui.radioButton_loadRaw.isChecked():
            # load raw files
            e11_file_name = str(self.ui.lineEdit_e11ScanFile.text())
            self.load_raw_file(e11_file_name, 'e11')
            e22_file_name = str(self.ui.lineEdit_e22ScanFile.text())
            self.load_raw_file(e22_file_name, 'e22')
            e33_file_name = str(self.ui.lineEdit_e33ScanFile.text())
            self.load_raw_file(e33_file_name, 'e33')

        else:
            # load saved files
            reduced_file_name = str(self.ui.lineEdit_reducedFile.text())
            data_key, message = self._core.load_strain_stress_file(file_name=reduced_file_name)
        # END-IF

        if data_key is None:
            gui_helper.pop_message(self, message, message_type='error')
        else:
            self._curr_data_key = data_key
        # END-IF

        return

    def do_load_peak_info_files(self):
        """
        load peak information files
        :return:
        """


        return

    @staticmethod
    def load_column_file(file_name):
        """ load a column file (most for test)
        :param file_name:
        :return: an numpy.ndarray
        """
        checkdatatypes.check_file_name(file_name, check_exist=True, is_dir=False)

        # open file
        col_file = open(file_name, 'r')
        lines = col_file.readline()
        col_file.close()

        # parse
        data_set_list = list()
        for line in lines:
            line = line.strip()
            if len(line) == 0 or line.startswith('#'):
                # empty line or comment line
                continue
            terms = line.split()

            line_values = numpy.ndarray(shape=(len(terms),), dtype='float')
            for iterm in range(len(terms)):
                line_values[iterm] = float(terms[iterm])

            data_set_list.append(line_values)
        # END-FOR

        data_set = numpy.array(data_set_list)

        return data_set

    def load_raw_file(self, file_name, direction):
        """
        load stress/strain raw file with peak fit information
        :param file_name:
        :param direction:
        :return:
        """
        # TODO - 20180801 - Implement
        data_key, message = self._core.load_stain_stress_source_file(file_name=file_name,
                                                                     direction=direction)

        return

    def save_stress_strain(self, file_type=None):
        """
        save the calculated strain/stress file
        :return:
        """
        if file_type is None:
            file_type = str(self.ui.comboBox_saveFileType.currentText())

        raise NotImplementedError('TO BE CONTINUED')

        return

    def export_stress_strain(self):
        """
        export the stress/strain to some other format for future analysis
        :return:
        """

    def evt_load_file_type(self):
        """
        triggered when the radio buttons selection for file type to load is changed.
        enable and disable file loading group accordingly
        :return:
        """
        # if mutex is on, leave the method
        if self._load_file_radio_mutex:
            return

        # set the mutex
        self._load_file_radio_mutex = True

        # enable and disable
        if self.ui.radioButton_loadRaw.isChecked():
            self.ui.groupBox_importRawFiles.setEnabled(True)
            self.ui.groupBox_importReducedFile.setEnabled(False)
        else:
            self.ui.groupBox_importReducedFile.setEnabled(True)
            self.ui.groupBox_importRawFiles.setEnabled(False)
        # END-IF-ELSE

        # release the mutex
        self._load_file_radio_mutex = False

        return

    def do_plot_sliced_3d(self):
        """
        slice loaded 3D stress/strain and plot
        :return:
        """
        slice_direction = str(self.ui.comboBox_sliceDirection.currentText()).lower()
        plot_term = str(self.ui.comboBox_plotParameterName.currentText())


    def set_items_to_plot(self):
        """

        :return:
        """
        try:
            items = self._core.strain_calculator.get_plot_items(self._curr_data_key)
        except RuntimeError as run_err:
            return False, run_err

        self.ui.comboBox_plotParameterName.clear()
        for item in items:
            self.ui.comboBox_plotParameterName.addItem(item)

        return

    def setup_window(self, pyrs_core):
        """ set up the texture analysis window
        :param pyrs_core:
        :return:
        """
        # check
        assert isinstance(pyrs_core, pyrs.core.pyrscore.PyRsCore), 'PyRS core {0} of type {1} must be a PyRsCore ' \
                                                                   'instance.'.format(pyrs_core, type(pyrs_core))

        self._core = pyrs_core

        return



