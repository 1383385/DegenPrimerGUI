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
QSettings, pyqtWrapperType
from PyQt4.QtGui import QApplication, QMainWindow, QGroupBox, \
QFileDialog, QPlainTextEdit, QFont, QMessageBox, QTextCursor, \
QLabel, QGridLayout, QSizePolicy, QTextCursor
from DegenPrimer.DegenPrimerConfig import DegenPrimerConfig
from DegenPrimer.Option import Option, OptionGroup
from DegenPrimer.StringTools import print_exception
from DegenPrimer.AnalysisTask import AnalysisTask
from DegenPrimer.DBManagementTask import DBManagmentTask
from DegenPrimer.OptimizationTask import OptimizationTask
from Widgets import SequenceTableWidget
from SubprocessThread import SubprocessThread
from Field import Field
import degen_primer_pipeline

try: import DegenPrimerUI_rc #qt resources for the UI
except: pass

class pyqtABCMeta(pyqtWrapperType, abc.ABCMeta): pass

class DegenPrimerGUI(DegenPrimerConfig, QMainWindow):
    '''Graphical User Interface for degen_primer'''
    __metaclass__ = pyqtABCMeta

    _ui_path = ('./', '/usr/local/share/degen_primer_gui/', '/usr/share/degen_primer_gui/')
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

    _skip_options     = ['list_db']

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
        for path in self._ui_path:
            try:
                uic.loadUi(QString.fromUtf8(path+self._ui_file), self)
                break
            except:
                print path+self._ui_file+' no such file.'
                pass
        if not self.centralWidget(): 
            raise OSError('Error: unable to locate ui file.')
        #fields
        Field.customize_field = self._customize_field
        self._fields = dict()
        #config and cwdir path choosers
        self._build_group_gui(self._config_group)
        #job-id label
        self._job_id_label = QLabel(self)
        self.configForm.addWidget(self._job_id_label)
        #all other options
        self._seq_db_box = None
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
        self._pipeline_thread.finished.connect(self.reload_sequence_db)
        self._pipeline_thread.finished.connect(self.unlock_buttons)
        self._pipeline_thread.update_timer.connect(self.update_timer)
        self._pipeline_thread.message_received.connect(self.write)
        self._pipeline_thread_stop.connect(self._pipeline_thread.stop)
        #restore GUI state
        self._restore_mainwindow_state()
    #end def
    
    
    def _field(self, option):
        if option.name in self._fields:
            return self._fields[option.name]
        else: return None
    #end def
    
        
    def _set_field(self, option, value):
        field = self._field(option)
        if field is None: return
        field.value = value
    #end def
    
    
    def _get_field(self, option):
        field = self._field(option)
        if field is None: return None
        return field.value
    #end def
    
    
    def _customize_field(self, option, field, label):
        #set style-sheets and fonts
        if option.name == 'sequence':
            font = QFont()
            font.setFamily('Monospace')
            field.setFont(font)
        #connect signals to slots
        elif option.name == 'sequence_db':
            field.textChanged.connect(self._list_seq_db)
        elif option.name == 'config':
            field.textChanged.connect(self._load_config)
        elif option.name == 'working_directory':
            field.setText(QString.fromUtf8(os.path.abspath(self._cwdir)))
            field.editingFinished.connect(self._check_cwdir_field)
    #end def
    
    
    @pyqtSlot('QString')
    def _list_seq_db(self, db_filename):
        db_filename     = unicode(db_filename)
        use_ids_field   = self._fields['use_sequences'].field
        db_group_layout = self._seq_db_box.layout()
        if db_filename and os.path.isfile(db_filename):
            label = QLabel('Sequences in database', self.centralWidget())
            label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
            db_table_widget = SequenceTableWidget(self.centralWidget())
            if db_table_widget.list_db(db_filename):
                db_group_layout.addWidget(label, 0, 0)
                db_group_layout.addWidget(db_table_widget, 0, 1)
                db_table_widget.send_ids.connect(use_ids_field.setText)
                use_ids_field.textChanged.connect(db_table_widget.set_ids)
                db_table_widget.set_ids(', '.join(use_ids_field.text()))
                db_table_widget.show()
            else:
                del db_table_widget
                db_group_layout.addWidget(label, 0, 0)
                db_group_layout.addWidget(QLabel('no sequences found', self.centralWidget()), 0, 1)
        else:
            db_table_widget = self.centralWidget().findChild(SequenceTableWidget)
            if db_table_widget is None: return
            db_table_label  = db_group_layout.itemAtPosition(0,0).widget()
            if db_table_label is not None: db_table_label.deleteLater()
            db_table_widget.deleteLater()
    #end def
    
    
    def _build_group_gui(self, group):
        grp_box    = QGroupBox(group.desc, self.configFormWidget)
        grp_box.setLayout(QGridLayout())
        if group.name == 'seq_db': self._seq_db_box = grp_box
        for opt in group.options:
            if opt.name in self._skip_options: continue
            self._fields[opt.name] = Field(opt, grp_box)
        self.configForm.addWidget(grp_box)
    #end def
            
    
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
    #end def
    
    
    def _override_option(self, option):
        if self._fields_empty: return None
        return self._get_field(option)
    #end def
        
    
    def _update_fields(self):
        for option in self._options:
            self._set_field(option, self._unscaled_value(option))
    #end def
    
    
    @pyqtSlot('QString')
    def parse_configuration(self, config_file=None):
        #parse configuration
        if config_file:
            DegenPrimerConfig.parse_configuration(self, unicode(config_file))
        else: DegenPrimerConfig.parse_configuration(self)
        #update form fields
        self._update_fields()
        self._fields_empty = False
    #end def
    
    
    @pyqtSlot()
    def reload_config(self): self._load_config(self._config_file)
        
    
    @pyqtSlot('QString')
    def load_config(self, config_file):
        old_config = self._get_field(self._config_option)
        if config_file != old_config:
            self._set_field(self._config_option, config_file)
        else:
            self._load_config(config_file)
    #end def

    
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
    #end def
    
    
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
    #end def
    
    
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
    #end def
    
    
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
    #end def
    
    
    def _parse(self):
        try:
            self.parse_configuration(self._config_file)
        except ValueError, e:
            self._fields_empty = False
            self.write('\n'+e.message)
            return False
        return True
    #end def
    
    
    def _parse_and_check(self):
        return self._parse() and AnalysisTask.check_options(self)
    #end def
    
    
    @pyqtSlot()
    def _analyse(self):
        #try to parse configuration and check it
        if not self._parse(): return
        if DBManagmentTask.check_options(self) \
        or OptimizationTask.check_options(self) \
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
    #end def
    
    
    @pyqtSlot(bool)
    def update_timer(self, time_string):
        self.elapsedTimeLineEdit.setText(time_string)
    #end def
    

    def _clear_results(self):
        while self.mainTabs.count() > 1:
            self.mainTabs.removeTab(1)
        self._reports = []
    #end def
    
    
    @pyqtSlot()
    def _reset_fields(self):
        self._set_field(self._config_option, '')
        self.terminalOutput.clear()
        self._clear_results()
        self._load_config(None)
    #end def
    
    
    def _show_run_specific_widgets(self, show=True):
        for widget in self._run_widgets:
            if show: widget.show()
            else: widget.hide()
    #end def
    
    #for pipeline thread to call
    #lock analyze and reset buttons while analysis is running
    @pyqtSlot(bool)
    def lock_buttons(self, lock=True):
        for widget in self._idle_widgets:
            widget.setEnabled(not lock)
        self._show_run_specific_widgets(lock)
    #end def
    @pyqtSlot()
    def unlock_buttons(self): self.lock_buttons(False)
    
    
    #show result tabs
    @pyqtSlot()
    def show_results(self):
        if not self._reports: return
        #display reports
        for report_name, report_file in self._reports:
            #load report
            report_widget = QPlainTextEdit()
            font = QFont()
            font.setFamily('Monospace')
            report_widget.setFont(font)
            report_widget.setReadOnly(True)
            try:
                report_file = open(report_file, 'r')
                report_text = report_file.read()
                report_file.close()
            except Exception, e:
                print 'Unable to load report file:', report_file
                print_exception(e)
                continue
            report_widget.insertPlainText(QString.fromUtf8(report_text))
            report_widget.moveCursor(QTextCursor.Start, QTextCursor.MoveAnchor)
            self.mainTabs.addTab(report_widget, report_name)
        #alert main window
        QApplication.alert(self)
    #end def
    
    
    @pyqtSlot()
    def reload_sequence_db(self, need_reload=True):
        if not need_reload: return
        self._list_seq_db(None)
        self._list_seq_db(self.sequence_db)
    #end def
        
        
    #stdout/err catcher
    def write(self, text):
        self.terminalOutput.moveCursor(QTextCursor.End)
        self._append_terminal_output.emit(QString.fromUtf8(text))
    #end def
        
    def flush(self): pass
        
        
    #abort handler
    @pyqtSlot()
    def _abort_analysis(self):
        if self._pipeline_thread.isRunning():
            self._pipeline_thread_stop.emit()
            self.abortButton.setEnabled(False)
            self.abortButton.setText('Aborting...')
    #end def
    
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
    #end def
#end class


#tests
import sys

if __name__ == '__main__':
    app = QApplication(sys.argv)
    main = DegenPrimerGUI()
    sys.stdout = main
    sys.stderr = main
    main.show()
    sys.exit(app.exec_())