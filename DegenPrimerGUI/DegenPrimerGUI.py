# Copyright (C) 2012 Allis Tauri <allista@gmail.com>
# 
# degen_primer is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# degen_primer_gui is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
'''
Created on Jul 27, 2012

@author: Allis Tauri <allista@gmail.com>
'''


import os
import abc
from PyQt4 import uic
from PyQt4.QtCore import QString, pyqtSlot, pyqtSignal, \
QSettings, pyqtWrapperType, Qt
from PyQt4.QtGui import QApplication, QMainWindow, QGroupBox, \
QFileDialog,  QFont, QMessageBox, QTextDocument, \
QLabel, QGridLayout, QTextCursor, QPushButton, \
QFrame, QTextEdit, QLineEdit, QShortcut, QKeySequence

from DegenPrimer.DegenPrimerConfig import DegenPrimerConfig
from DegenPrimer.Option import Option, OptionGroup
from DegenPrimer.AnalysisTask import AnalysisTask
from DegenPrimer.OptimizationTask import OptimizationTask

from .Widgets import SequenceTableView
from .SubprocessThread import SubprocessThread
from .Field import Field
import degen_primer_pipeline

try: import DegenPrimerUI_rc #qt resources for the UI
except: pass

class pyqtABCMeta(pyqtWrapperType, abc.ABCMeta): pass

class DegenPrimerGUI(DegenPrimerConfig, QMainWindow):
    '''Graphical User Interface for degen_primer'''
    __metaclass__ = pyqtABCMeta

    _ui_path = ('./', 'resources/', '/usr/local/share/degen_primer_gui/', '/usr/share/degen_primer_gui/')
    _ui_file = 'DegenPrimerUI.ui'
    
    _config_option = Option(name='config',
                            desc='Path to a configuration file containing some '
                            'or all of the options listed below.',
                            nargs=1,
                            py_type=str,
                            field_type='file',
                            )
    _cwdir_option  = Option(name='working_directory',
                            desc='Directory where degen_primer will be executed '
                            'and where all the reports will be saved. IMPORTANT: If you are loading '
                            'configuration from a .cfg file, working directory is automatically set to '
                            'the directory containing the file in order to maintain correct '
                            'relative paths that it may contain.',
                            nargs=1,
                            py_type=str,
                            field_type='directory',
                            )
    _config_group = OptionGroup('config_group',
                                'Configuration and working directory',
                                options=(_config_option,
                                         _cwdir_option,
                                         ))
    _skip_options     = []

    #stdout/err catcher signal
    _append_terminal_output = pyqtSignal(str)
    #signal to abort computations
    _pipeline_thread_stop   = pyqtSignal()
    
    
    #constructor
    def __init__(self):
        #parent's constructors
        DegenPrimerConfig.__init__(self)
        QMainWindow.__init__(self)
        #working directory
        self._cwdir = os.getcwd()
        #session independent configuration
        self._settings = QSettings()
        #try to load UI
        self.load_ui(self._ui_file, self)
        #fields
        Field.customize_field = self._customize_field
        self._fields = dict()
        #config and cwdir path choosers
        self._build_group_gui(self._config_group)
        #job-id label
        self._job_id_label = QLabel(self)
        self.configForm.addWidget(self._job_id_label)
        #sequence db view
        self._loaded_files = []
        self._seq_db_widget = None
        self._seq_db_box = None
        self._seq_db_button = None
        for group in self._option_groups: self._build_group_gui(group)
        #setup default values
        self._reset_fields()
        #setup buttons
        self._run_widgets  = (self.abortButton, 
                              self.elapsedTimeLineEdit,
                              self.elapsedTimeLabel,)
        self._idle_widgets = (self.saveButton,
                              self.runButton,
                              self.resetButton,
                              self.reloadButton,)
        self.reloadButton.clicked.connect(self.reload_config)
        self.resetButton.clicked.connect(self._reset_fields)
        self.saveButton.clicked.connect(self._save_config)
        self.runButton.clicked.connect(self._analyse)
        self.abortButton.clicked.connect(self._abort_analysis)
        self._show_run_specific_widgets(False)
        #setup terminal output
        self._append_terminal_output.connect(self.terminalOutput.insertPlainText)
        self.terminalOutput.textChanged.connect(self.terminalOutput.ensureCursorVisible)
        #pipeline thread
        self._pipeline_thread = SubprocessThread(degen_primer_pipeline)
        self._pipeline_thread.started.connect(self.lock_buttons)
        self._pipeline_thread.results_received.connect(self.register_reports)
        self._pipeline_thread.finished.connect(self.show_results)
        self._pipeline_thread.finished.connect(self.unlock_buttons)
        self._pipeline_thread.update_timer.connect(self.update_timer)
        self._pipeline_thread.message_received.connect(self.show_message)
        self._pipeline_thread_stop.connect(self._pipeline_thread.stop)
        #restore GUI state
        self._restore_mainwindow_state()
    #end def
    
    
    def _field(self, option):
        if option.name in self._fields:
            return self._fields[option.name]
        else: return None
        
    def _set_field(self, option, value):
        field = self._field(option)
        if field is None: return
        field.value = value
    
    def _get_field(self, option):
        field = self._field(option)
        if field is None: return None
        return field.value
    
    
    def _customize_field(self, option, field, label):
        #set style-sheets and fonts
        if option.name == 'sequence':
            font = QFont()
            font.setFamily('Monospace')
            field.setFont(font)
        #connect signals to slots
        elif option.name == 'config':
            field.textChanged.connect(self._load_config)
        elif option.name == 'working_directory':
            field.setText(QString.fromUtf8(os.path.abspath(self._cwdir)))
            field.editingFinished.connect(self._check_cwdir_field)
        elif option.name == 'template_files':
            field.textChanged.connect(self._del_seq_db_if_changed)
    
    
    def _del_seq_db(self):
        if self._seq_db_widget is not None:
            if self._seq_db_widget.loading:
                self._seq_db_widget.abort_loading.emit()
            self._seq_db_widget.deleteLater()
        self._seq_db_widget = None
        self._seq_db_button.setText('Show Sequence Selector')
    
    def _del_seq_db_if_changed(self):
        cur_files = self._fields['template_files'].value
        if len(self._loaded_files) != len(cur_files):
            self._del_seq_db()
            return
        for old, new in zip(self._loaded_files, cur_files):
            if old != new:
                self._del_seq_db()
                return 
    
    def _toggle_seq_db_widget(self):
        if self._seq_db_widget is None: return
        if self._seq_db_widget.isHidden():
            self._seq_db_widget.show()
            self._seq_db_button.setText('Hide Sequence Selector')
        else: 
            self._seq_db_widget.hide()
            self._seq_db_button.setText('Show Sequence Selector')
        
        
    @pyqtSlot()
    def _seq_db_loaded(self):
        self._seq_db_widget.set_ids(', '.join(self._fields['use_sequences'].field.text()))
        self._seq_db_button.setText('Hide Sequence Selector')
    
    def _load_seq_db(self, filenames):
        if not filenames: return
        self._loaded_files = filenames
        self._seq_db_button.setText('Loading sequences, please wait...')
        self._seq_db_widget = SequenceTableView(self.centralWidget())
        self._seq_db_widget.loaded.connect(self._seq_db_loaded)
        self._seq_db_widget.load_db(filenames)
        db_group_layout = self._seq_db_box.layout()
        use_ids_field   = self._fields['use_sequences'].field
        row = db_group_layout.rowCount()
        db_group_layout.addWidget(self._seq_db_widget, row, 1)
        self._seq_db_widget.send_ids.connect(use_ids_field.setText)
        use_ids_field.textChanged.connect(self._seq_db_widget.set_ids)        


    def _setup_seq_db_view(self, grp_box):
        self._seq_db_box = grp_box
        self._seq_db_button = QPushButton('Show Sequence Selector', self.centralWidget())
        self._seq_db_button.clicked.connect(self._toggle_seq_db)
        layout = self._seq_db_box.layout() 
        layout.addWidget(self._seq_db_button, layout.rowCount(), 1)
    
    def _build_group_gui(self, group):
        grp_box    = QGroupBox(group.desc, self.configFormWidget)
        grp_box.setLayout(QGridLayout())
        for opt in group.options:
            if opt.name in self._skip_options: continue
            self._fields[opt.name] = Field(opt, grp_box)
        self.configForm.addWidget(grp_box)
        #customization
        if group.name == 'iPCR': 
            self._setup_seq_db_view(grp_box)

    
    def _save_mainwindow_state(self):
        self._settings.beginGroup('main_window')
        self._settings.setValue('size', self.size())
        self._settings.setValue('splitter_state', self.terminalSplitter.saveState())
        self._settings.endGroup()
    #end def
    
    
    def _restore_mainwindow_state(self):
        self._settings.beginGroup('main_window')
        size = self._settings.value('size', defaultValue=None)
        if size != None:
            self.resize(size.toSize())
        splitter_state = self._settings.value('splitter_state', defaultValue=None)
        if splitter_state != None:
            self.terminalSplitter.restoreState(splitter_state.toByteArray())
        self._settings.endGroup()
    
    
    def _override_option(self, option):
        if self._fields_empty: return None
        return self._get_field(option)
        
    
    def _update_fields(self):
        for option in self._options:
            self._set_field(option, self._unscaled_value(option))
    
    
    @pyqtSlot('QString')
    def parse_configuration(self, config_file=None):
        #parse configuration
        if config_file:
            DegenPrimerConfig.parse_configuration(self, unicode(config_file))
        else: DegenPrimerConfig.parse_configuration(self)
        #update form fields
        self._update_fields()
        self._fields_empty = False
    
    
    @pyqtSlot()
    def reload_config(self): self._load_config(self._config_file)
        
    
    @pyqtSlot('QString')
    def load_config(self, config_file):
        old_config = self._get_field(self._config_option)
        if config_file != old_config:
            self._set_field(self._config_option, config_file)
        else:
            self._load_config(config_file)

    
    @pyqtSlot('QString')
    def _load_config(self, config_file):
        self._fields_empty = True
        self.terminalOutput.clear()
        self._clear_results()
        if config_file and os.path.isfile(unicode(config_file)): 
            self._cwdir = os.path.dirname(unicode(config_file)) or '.'
            self._set_field(self._cwdir_option, 
                            os.path.abspath(self._cwdir))
            os.chdir(self._cwdir)
        self._config_file = config_file
        self._parse_and_check()
        self._job_id_label.setText(('<p align=center><b>Analysis ID:</b> '
                                    '%s</p>') % self.job_id) 
    
    
    @pyqtSlot()
    def _save_config(self):
        #try to parse configuration and check it
        if not self._parse_and_check(): return
        #set working directory
        self._change_cwdir()
        #save configuration to the file
        self.save_configuration()
        #load saved configuration
        self.load_config(self._config_file)
    
    
    @pyqtSlot()
    def _check_cwdir_field(self):
        cwdir = self._get_field(self._cwdir_option)
        if cwdir:
            if not os.path.isdir(cwdir):
                print '\nNo such directory: %s\n' % cwdir
            else:
                if cwdir != self._cwdir:
                    self._cwdir = cwdir
                    print '\nWorking directory will be set to: %s\n' % self._cwdir
    
    
    def _change_cwdir(self):
        cwdir = self._get_field(self._cwdir_option)
        while not os.path.isdir(cwdir):
            file_dialog = QFileDialog(None, 'Select a directory to save reports to...')
            self._restore_dialog_state(self._cwdir_option, file_dialog)
            file_dialog.setFileMode(QFileDialog.Directory)
            file_dialog.setOption(QFileDialog.ShowDirsOnly, True)
            file_dialog.setModal(True)
            file_dialog.fileSelected.connect(self._cwdir_option.field.setText)
            file_dialog.exec_()
            cwdir = self._get_field(self._cwdir_option)
        self._cwdir = cwdir
        os.chdir(self._cwdir)
        print '\nWorking directory is %s\n' % os.getcwd()
    
    
    def _parse(self):
        try:
            self.parse_configuration(self._config_file)
        except ValueError, e:
            self._fields_empty = False
            self.write('\n'+e.message)
            return False
        return True
    
    def _parse_and_check(self):
        return self._parse() and AnalysisTask.check_options(self)
    
    
    @pyqtSlot()
    def _analyse(self):
        #try to parse configuration and check it
        if not self._parse(): return
        if OptimizationTask.check_options(self) \
        or AnalysisTask.check_options(self):
            self._pipeline_thread.set_data(self.options)
            if self._config_file:
                self._change_cwdir()
                self.save_configuration(silent=True)
                self.load_config(self._config_file)
            else: 
                self.terminalOutput.clear()
                self.reset_temporary_options()
                self._update_fields()
            self.abortButton.setEnabled(True)
            self.abortButton.setText('Abort')
            self._pipeline_thread.start()
    
    
    @pyqtSlot(bool)
    def update_timer(self, time_string):
        self.elapsedTimeLineEdit.setText(time_string)
    

    def _clear_results(self):
        while self.mainTabs.count() > 1:
            self.mainTabs.removeTab(1)
        self._reports = []
        self._del_seq_db()
    
    
    @pyqtSlot()
    def _reset_fields(self):
        self._set_field(self._config_option, '')
        self.terminalOutput.clear()
        self._clear_results()
        self._load_config(None)
    
    
    def _show_run_specific_widgets(self, show=True):
        for widget in self._run_widgets:
            if show: widget.show()
            else: widget.hide()
    
    #for pipeline thread to call
    #lock analyze and reset buttons while analysis is running
    @pyqtSlot(bool)
    def lock_buttons(self, lock=True):
        for widget in self._idle_widgets:
            widget.setEnabled(not lock)
        self._show_run_specific_widgets(lock)

    @pyqtSlot()
    def unlock_buttons(self): self.lock_buttons(False)
    
    @classmethod
    def load_ui(cls, ui_file, widget):
        npaths = len(cls._ui_path)
        for i, path in enumerate(cls._ui_path):
            try:
                filepath = os.path.join(path, ui_file)
                uic.loadUi(QString.fromUtf8(filepath), widget)
                break
            except (OSError, IOError):
                if i == npaths-1:
                    raise OSError('Error: unable to locate %s.' % ui_file)

    class ReportWidget(QFrame):
        _ui_file = 'ReportWidget.ui'
        
        def __init__(self, parent=None):
            QFrame.__init__(self, parent=parent)
            DegenPrimerGUI.load_ui(self._ui_file, self)
            self.editor = self.findChild(QTextEdit, 'ReportTextEdit')
            self.search = self.findChild(QLineEdit, 'SearchLineEdit')
            self.search.textChanged.connect(self.find_text)
            self.search.returnPressed.connect(self.find_next)
            QShortcut(QKeySequence(Qt.Key_F3), self, self.find_next)
            QShortcut(QKeySequence(Qt.Key_F2), self, self.find_prev)
            self.term = ''

        @pyqtSlot('QString')
        def find_text(self, qstring):
            self.term = str(qstring)
            self.find_next()
            
        @pyqtSlot()
        def find_next(self):
            if not self.term: return
            self.editor.find(self.term)
            
        @pyqtSlot()
        def find_prev(self):
            if not self.term: return
            self.editor.find(self.term, QTextDocument.FindBackward)
    
    #show result tabs
    @pyqtSlot()
    def show_results(self):
        if not self._reports: return
        #display reports
        for report_name, report_file in self._reports:
            #load report
            report_widget = self.ReportWidget(self.centralWidget())
            try:
                report_file = open(report_file, 'r')
                report_text = report_file.read()
                report_file.close()
            except Exception, e:
                print 'Unable to load report file:', report_file
                print e
                continue
            report_widget.editor.insertPlainText(QString.fromUtf8(report_text))
            report_widget.editor.moveCursor(QTextCursor.Start, QTextCursor.MoveAnchor)
            self.mainTabs.addTab(report_widget, report_name)
        #alert main window
        QApplication.alert(self)
    
    @pyqtSlot()
    def _toggle_seq_db(self):
        if self._seq_db_widget is None:
            self._load_seq_db(self._fields['template_files'].value)
        else: self._toggle_seq_db_widget()
        
    @pyqtSlot(str)
    def show_message(self, text):
        self.terminalOutput.moveCursor(QTextCursor.End)
        self._append_terminal_output.emit(QString.fromUtf8(text))
        
    #abort handler
    @pyqtSlot()
    def _abort_analysis(self):
        if self._pipeline_thread.isRunning():
            self._pipeline_thread_stop.emit()
            self.abortButton.setEnabled(False)
            self.abortButton.setText('Aborting...')
    
    #close handler
    def closeEvent(self, event):
        if self._pipeline_thread.isRunning():
            if QMessageBox.question(None, '', 'The analysis thread is still running. '
                                    'If you quit now a loss of data may occure.\n'
                                    'Are you sure you want to quit?',
                                    QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No) == QMessageBox.Yes:
                del self._pipeline_thread
            else: 
                event.ignore()
                return
        self._save_mainwindow_state() 
        event.accept()
#end class