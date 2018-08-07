from mplgraphicsview1d import MplGraphicsView1D
from mplgraphicsview2d import MplGraphicsView2D
from mplgraphicsviewpolar import MplGraphicsPolarView
import numpy as np
import mplgraphicsviewpolar


class Diffraction2DPlot(MplGraphicsPolarView):
    """
    General 2D plot view for diffraction data set
    """
    def __init__(self, parent):
        """
        initialization
        :param parent:
        """
        super(Diffraction2DPlot, self).__init__(parent)

        return

    def plot_pole_figure(self, vec_alpha, vec_beta, vec_intensity):
        """
        plot pole figure in contour
        :param vec_alpha:
        :param vec_beta:
        :param vec_intensity:
        :return:
        """
        # check inputs which are only mattering here
        mplgraphicsviewpolar.check_1D_array(vec_alpha)

        # clear the image
        print ('[DB...BAT] Plot pole figure for {0} data points!'.format(len(vec_alpha)))
        # self._myCanvas.axes.clear()

        # project vector to XY plane, i.e., convert alpha (phi) azimuthal angle to r
        vec_r = np.sin(vec_alpha * np.pi / 180.)
        vec_intensity = np.log(vec_intensity+1.)

        #     def plot_contour(self, vec_theta, vec_r, vec_values, max_r, r_resolution, theta_resolution):
        self._myCanvas.plot_contour(vec_theta=vec_beta, vec_r=vec_r, vec_values=vec_intensity, max_r=1.,
                                    r_resolution=0.05, theta_resolution=3.)

        self.show()

        return


class DiffContourView(MplGraphicsView2D):
    """
    Diffraction contour viewer
    """
    def __init__(self, parent):
        """
        initialization
        :param parent:
        """
        super(DiffContourView, self).__init__(parent)


class GeneralDiffDataView(MplGraphicsView1D):
    """
    generalized diffraction view
    """
    def __init__(self, parent):
        """
        blabla
        :param parent:
        """
        super(GeneralDiffDataView, self).__init__(parent)

        # management
        self._line_reference_list = list()
        self._last_line_reference = None
        self._current_x_axis_name = None

        return

    @property
    def current_x_name(self):
        """

        :return:
        """
        return self._current_x_axis_name

    def plot_scatter(self, vec_x, vec_y, x_label, y_label):
        """ plot figure in scatter-style
        :param vec_x:
        :param vec_y:
        :param x_label:
        :param y_label:
        :return:
        """
        # TODO Future: Need to write use cases.  Now it is for demo
        # It is not allowed to plot 2 plot with different x-axis
        if self._last_line_reference is not None:
            if x_label != self.get_label_x():
                self.reset_viewer()

        # plot data in a scattering plot
        ref_id = self.add_plot(vec_x, vec_y, line_style='', marker='.',
                               color='red', x_label=x_label, y_label=y_label)
        self._line_reference_list.append(ref_id)
        self._last_line_reference = ref_id
        self._current_x_axis_name = x_label

        return

    def reset_viewer(self):
        """
        reset current graphics view
        :return:
        """
        # reset all the management data structures
        self._last_line_reference = None
        self._line_reference_list = list()

        # call to clean lines
        self.clear_all_lines(row_number=0, col_number=0, include_right=False)

        return


class PeakFitSetupView(MplGraphicsView1D):
    """
    Matplotlib graphics view to set up peak fitting
    """
    def __init__(self, parent):
        """
        Graphics view for peak fitting setup
        :param parent:
        """
        super(PeakFitSetupView, self).__init__(parent)

        # management
        self._diff_reference_list = list()
        self._last_diff_reference = None  # last diffraction (raw) line ID
        self._last_model_reference = None  # last model diffraction (raw) line ID
        self._last_fit_diff_reference = None  # TODO

        #
        self._auto_color = True

        return

    def _next_color(self):
        # TODO Implement ASAP
        return 'blue'

    def plot_diff_data(self, diff_data_set, data_reference):
        """
        plot a diffraction data
        :param diff_data_set:
        :param data_reference: reference name for the data to plot
        :return:
        """
        # parse the data
        vec_x = diff_data_set[0]
        vec_y = diff_data_set[1]

        # plot data
        ref_id = self.add_plot(vec_x, vec_y, color=self._next_color(), x_label='$2\\theta (degree)$', marker=None,
                               show_legend=True, y_label=data_reference)

        self._diff_reference_list.append(ref_id)
        self._last_diff_reference = ref_id

        return

    def plot_fit_diff(self, diff_data_set, model_data_set):
        """
        plot the difference between fitted diffraction data (model) and experimental data
        :param diff_data_set:
        :param model_data_set:
        :return:
        """
        # check input
        assert isinstance(diff_data_set, tuple) and len(diff_data_set) >= 2, 'Diffraction data set {} ' \
                                                                             'must be a 2-tuple but not a {}' \
                                                                             ''.format(diff_data_set,
                                                                                       type(diff_data_set))
        assert isinstance(model_data_set, tuple) and len(model_data_set) >= 2,\
            'Model data set {} must be a 2-tuple but not a {}'.format(model_data_set, type(model_data_set))

        # remove previous difference curve
        if self._last_fit_diff_reference is not None:
            self.remove_line(row_index=0, col_index=0, line_id=self._last_fit_diff_reference)
            self._last_fit_diff_reference = None

        # calculate
        fit_diff_vec = diff_data_set[1] - model_data_set[1]

        # plot
        self._last_fit_diff_reference = self.add_plot(diff_data_set[0], fit_diff_vec, color='green')

        return

    def plot_model(self, model_data_set):
        """
        plot a model diffraction data
        :param model_data_set:
        :return:
        """
        # check condition
        if len(self._diff_reference_list) > 1:
            # very confusion to plot model
            print ('There are more than 1 raw data plot.  It is very confusing to plot model.'
                   '\n FYI current diffraction data references: {0}'.format(self._diff_reference_list))
            raise RuntimeError('There are more than 1 raw data plot.  It is very confusing to plot model.')

        # remove previous model
        if self._last_model_reference is not None:
            print ('[DB...BAT] About to remove last reference: {0}'.format(self._last_model_reference))
            self.remove_line(row_index=0, col_index=0, line_id=self._last_model_reference)
            self._last_model_reference = None

        # plot
        self._last_model_reference = self.add_plot(model_data_set[0], model_data_set[1], color='red')

        return

    def reset_viewer(self):
        """
        reset current graphics view
        :return:
        """
        # reset all the management data structures
        self._last_model_reference = None
        self._last_diff_reference = None
        self._last_fit_diff_reference = None
        self._diff_reference_list = list()

        # call to clean lines
        self.clear_all_lines(row_number=0, col_number=0, include_main=True, include_right=False)

        return


class SampleSliceView(MplGraphicsView2D):
    """
    2D contour view for sliced sample
    """
    def __init__(self, parent):
        """
        initialization
        :param parent:
        """
        super(SampleSliceView, self).__init__(parent)

        return
