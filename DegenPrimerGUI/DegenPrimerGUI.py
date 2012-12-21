# Copyright (C) 2012 Allis Tauri <allista@gmail.com>
# 
# degen_primer is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# indicator_gddccontrol is distributed in the hope that it will be useful, but
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
import errno
from math import log, ceil, floor
from PyQt4 import uic
from PyQt4.QtCore import QObject, QThread, QString, pyqtSlot, pyqtSignal, \
QSettings
from PyQt4.QtGui import QApplication, QMainWindow, QFormLayout, QGroupBox, \
QLineEdit, QDoubleSpinBox, QSpinBox, QCheckBox, QFileDialog, QPushButton, \
QPlainTextEdit, QFont, QMessageBox, QTextCursor
from DegenPrimer.DegenPrimerConfig import DegenPrimerConfig
from DegenPrimer.DegenPrimerPipeline import DegenPrimerPipeline #, capture_to_queue
from DegenPrimer.StringTools import wrap_text, print_exception
import DegenPrimerUI_rc #qt resources for the UI


class DegenPrimerPipelineThread(QThread):
    '''Wrapper for degen_primer_pipeline with multi-threading'''
    
    #signals for the main thread
    _lock_buttons   = pyqtSignal(bool)
    _show_results   = pyqtSignal()
    
    
    def __init__(self, args):
        QThread.__init__(self)
        self._args     = args
        self._pipeline = DegenPrimerPipeline()
        self._lock_buttons.connect(self._args.lock_buttons)
        self._show_results.connect(self._args.show_results)
    #end def
    
    
    def __del__(self):
        self._pipeline.terminate()
    #end def
    
    
    def run(self):
        self._lock_buttons.emit(True)
        success = False
        try:
            success = self._pipeline.run(self._args)
        #EOF means that some subroutine was terminated in the Manager process
        except EOFError: pass
        #IO code=4 means the same
        except IOError, e:
            if e.errno == errno.EINTR: pass
            else:
                self._pipeline.terminate()
                print '\nException has occured while executing DegenPrimer Pipeline. Please, try again.'
                print_exception(e)
        except Exception, e:
            self._pipeline.terminate()
            print '\nException has occured while executing DegenPrimer Pipeline. Please, try again.'
            print_exception(e)
        if success: self._show_results.emit()
        self._lock_buttons.emit(False)
    #end def
    
    
    @pyqtSlot()
    def stop(self):
        self._pipeline.terminate()
#end class


class LineEditWrapper(QObject):
    '''Wrapper for QLineEdit which overloads setText 
    so as to make it accept list of strings'''
    def __init__(self, parent):
        if type(parent) != QLineEdit:
            raise ValueError('Parent for LineEditWrapper should be an instance of QLineEdit.')
        QObject.__init__(self, parent)
    
    @pyqtSlot('QStringList')
    def setText(self, strings):
        text = ''
        for s in strings:
            if text: text += ', '
            text += unicode(s)
        self.parent().setText(QString.fromUtf8(text))
    #end def
    
    def text(self):
        text = unicode(self.parent().text())
        return text.split(', ')
    #end def
#end class


class DegenPrimerGUI(DegenPrimerConfig, QMainWindow):
    '''Graphical User Interface for degen_primer'''

    _ui_path = ('./', '/usr/local/share/degen_primer_gui/', '/usr/share/degen_primer_gui/')
    _ui_file        = 'DegenPrimerUI.ui'
    _config_option  = {'option':'config_file',
                               'section'   :'config',
                               #number of arguments
                               'nargs'     :1,
                               #help string
                               'help'      :'Path to a configuration file containing some '
                                'or all of the options listed below.',
                               #type
                               'field_type':'file', #for gui
                               #default value
                               'default'   :None}
    _cwdir_option   = {'option':'working_directory',
                               'section'   :'config',
                               #number of arguments
                               'nargs'     :1,
                               #help string
                               'help'      :'Directory where degen_primer will be executed '
                               'and where all the reports will be saved. IMPORTANT: If you are loading '
                               'configuration from a .cfg file, working directory is automatically set to '
                               'the directory containing the file in order to maintain correct '
                               'relative paths that it may contain.',
                               #type
                               'field_type':'directory', #for gui
                               #default value
                               'default'   :None}


    #stdout/err catcher signal
    _append_terminal_output = pyqtSignal(str)
    #signal to abort computations
    _pipeline_thread_stop   = pyqtSignal()
    
    
    #utility classmethods
    @classmethod
    def _trigger(cls, func, *f_args, **f_kwargs):
        '''wrap particular function call into a trigger function'''
        def wrapped(*args, **kwargs):
            return func(*f_args, **f_kwargs)
        return wrapped
    
    
    #constructor
    def __init__(self):
        #parent's constructors
        DegenPrimerConfig.__init__(self)
        QMainWindow.__init__(self)
        #session independent configuration
        self._settings = QSettings()
        #setup configuration group
        self._groups[self._config_option['section']] = 'Configuration'
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
        #assemble config form
        self._group_boxes = dict()
        self._fields      = dict()
        #config file chooser
        self._setup_option_field(self._config_option)
        self._setup_option_field(self._cwdir_option)
        self._fields[self._config_option['option']].textChanged.connect(self._load_config)
        #all other options
        for option in self._options:
            self._setup_option_field(option)
        #setup default values
        self._reset_fields()
        #setup reset button
        self.resetButton.clicked.connect(self._reset_fields)
        #setup analyse button
        self.analyseButton.clicked.connect(self._analyse)
        #setup abort button
        self.abortButton.clicked.connect(self._abort_analysis)
        self.abortButton.hide()
        #setup terminal output
        self._append_terminal_output.connect(self.terminalOutput.insertPlainText)
        self.terminalOutput.textChanged.connect(self.terminalOutput.ensureCursorVisible)
        #pipeline thread
        self._pipeline_thread = DegenPrimerPipelineThread(self)
        self._pipeline_thread_stop.connect(self._pipeline_thread.stop)
        #restore GUI state
        self._restore_mainwindow_state()
    #end def
    
    
    def _setup_option_field(self, option):
        field = None
        label = ''
        if option['field_type'] == 'string':
            field = QLineEdit(self.centralWidget())
            label = option['option'].replace('_', ' ')
            if self._multiple_args(option):
                field_wrapper = LineEditWrapper(field)
        elif option['field_type'] == 'float':
            field = QDoubleSpinBox(self.centralWidget())
            label = option['option'].replace('_', ' ')
            if option['metavar']:
                label += (' (%s)' % option['metavar'])
            field.setMinimum(float(option['limits'][0]))
            field.setMaximum(float(option['limits'][1]))
            if float(option['limits'][0]) > 0:
                decimals = max(ceil(-1*log(option['limits'][0], 10)), 2)
            else: decimals = 2
            field.setDecimals(decimals)
            field.setSingleStep(1.0/(10**ceil(decimals/2.0)))
        elif option['field_type'] == 'integer':
            field = QSpinBox(self.centralWidget())
            label = option['option'].replace('_', ' ')
            if option['metavar']:
                label += (' (%s)' % option['metavar'])
            field.setMinimum(int(option['limits'][0]))
            field.setMaximum(int(option['limits'][1]))
        elif option['field_type'] == 'boolean':
            field = QCheckBox(self.centralWidget())
            label = option['option'].replace('_', ' ')
        elif option['field_type'] == 'file' \
        or   option['field_type'] == 'directory':
            field = QLineEdit(self.centralWidget())
            label = QPushButton(option['option'].replace('_', ' '), self.centralWidget())
            file_dialog = QFileDialog(self.centralWidget(), option['option'].replace('_', ' '))
            #try to restore dialog state
            self._restore_dialog_state(option, file_dialog)
            #prepare a slot to save state
            save_state_slot = self._trigger(self._save_dialog_state, option, file_dialog)
            file_dialog.currentChanged.connect(save_state_slot)
            #button-label
            label.clicked.connect(file_dialog.show)
            if option['field_type'] == 'file':
                if self._multiple_args(option):
                    file_dialog.setFileMode(QFileDialog.ExistingFiles)
                    field_wrapper = LineEditWrapper(field)
                    file_dialog.filesSelected.connect(field_wrapper.setText)
                else:
                    file_dialog.fileSelected.connect(field.setText)
            else:
                file_dialog.setFileMode(QFileDialog.Directory)
                file_dialog.setOption(QFileDialog.ShowDirsOnly, True)
                file_dialog.fileSelected.connect(field.setText)
                field.textChanged.connect(file_dialog.setDirectory)
        if field:
            #setup group box if necessary
            if option['section'] not in self._group_boxes:
                group_box = QGroupBox(self._groups[option['section']], self.centralWidget())
                self._group_boxes[option['section']] = QFormLayout(group_box)
                self.configForm.addWidget(group_box)
            #add a field to the layout
            field.setToolTip(wrap_text(option['help'].replace('%%', '%')))
            self._fields[option['option']] = field
            self._group_boxes[option['section']].addRow(label, field)
    #end def
    

    def _save_dialog_state(self, option, dialog):
        self._settings.setValue(option['option']+'/dialog_state', 
                                dialog.saveState())
        self._settings.setValue(option['option']+'/size', 
                                dialog.size())
        self._settings.setValue(option['option']+'/directory', 
                                dialog.directory().absolutePath())
        self._settings.setValue('sidebar_urls', dialog.sidebarUrls())
    #end def

    
    def _restore_dialog_state(self, option, dialog):
        dialog_state = self._settings.value(option['option']+'/dialog_state', defaultValue=None)
        if dialog_state != None:
            dialog.restoreState(dialog_state.toByteArray())
        dialog_size  = self._settings.value(option['option']+'/size', defaultValue=None)
        if dialog_size != None:
            dialog.resize(dialog_size.toSize())
        dialog_dir   = self._settings.value(option['option']+'/directory', defaultValue=None)
        if dialog_dir != None:
            dialog.setDirectory(dialog_dir.toString())
        sidebar_urls = self._settings.value('sidebar_urls', defaultValue=None)
        if sidebar_urls != None:
            urls = [url.toUrl() for url in sidebar_urls.toList()]
            dialog.setSidebarUrls(urls)
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


    def _override_option(self, option):
        if self._fields_empty: return None
        value_override = None
        #update field
        if option['field_type'] == 'string' \
        or option['field_type'] == 'file':
            if option['nargs'] == 1:
                value_override = unicode(self._fields[option['option']].text())
            else:
                value_override = self._fields[option['option']].findChild(LineEditWrapper).text()
        elif option['field_type'] == 'float' \
        or   option['field_type'] == 'integer':
            value_override = self._fields[option['option']].value()
        elif option['field_type'] == 'boolean':
            value_override = self._fields[option['option']].isChecked()
        return value_override
    #end def
    
    
    @pyqtSlot('QString')
    def parse_configuration(self, config_file=None):
        #parse configuration
        if config_file:
            DegenPrimerConfig.parse_configuration(self, unicode(config_file))
        else: DegenPrimerConfig.parse_configuration(self)
        #update form fields
        for option in self._options:
            #get value
            value = self._unscale_value(option)
            #update field
            if option['field_type'] == 'string' \
            or option['field_type'] == 'file':
                if not value: value = ''
                if option['nargs'] == 1:
                    self._fields[option['option']].setText(QString.fromUtf8(value))
                else:
                    self._fields[option['option']].findChild(LineEditWrapper).setText(value)
            elif option['field_type'] == 'float' \
            or   option['field_type'] == 'integer':
                if value is None: value = 0
                self._fields[option['option']].setValue(value)
            elif option['field_type'] == 'boolean':
                if value is None: value = False
                self._fields[option['option']].setChecked(value)
        self._fields_empty = False
    #end def
    
    
    @pyqtSlot('QString')
    def _load_config(self, config_file):
        self._fields_empty = True
        self.parse_configuration(config_file)
        if config_file and os.path.exists(os.path.dirname(unicode(config_file))):
            self._fields[self._cwdir_option['option']].setText(QString.fromUtf8(os.path.dirname(unicode(config_file))))
    #end def
    
    def load_config(self, config_file):
        self._fields[self._config_option['option']].setText(QString.fromUtf8(unicode(config_file)))
    
    
    def _clear_results(self):
        while self.mainTabs.count() > 1:
            self.mainTabs.removeTab(1)
        self._reports = list()
    #end def
    
    
    @pyqtSlot()
    def _reset_fields(self):
        self._fields[self._config_option['option']].setText('')
        self.terminalOutput.clear()
        self._clear_results()
        self._load_config(None)
    #end def
    
    
    @pyqtSlot()
    def _analyse(self):
        #clear terminal and results
        self.terminalOutput.clear()
        self._clear_results()
        #configuration file and working directory
        self._config_file = unicode(self._fields[self._config_option['option']].text())
        cwdir_field = self._fields[self._cwdir_option['option']]
        cwdir = unicode(cwdir_field.text())
        while not os.path.isdir(cwdir):
            file_dialog = QFileDialog(None, 'Select a directory to save reports to...')
            self._restore_dialog_state(self._cwdir_option, file_dialog)
            file_dialog.setFileMode(QFileDialog.Directory)
            file_dialog.setOption(QFileDialog.ShowDirsOnly, True)
            file_dialog.setModal(True)
            file_dialog.fileSelected.connect(cwdir_field.setText)
            file_dialog.exec_()
            cwdir = unicode(cwdir_field.text())
        os.chdir(cwdir)
        #load configuration
        print 'Current directory is %s\n' % os.getcwd()
        try:
            self.parse_configuration(self._config_file)
        except ValueError, e:
            self.write(e.message)
            return
        #reset do_blast and run_ipcress flags in the GUI
        self._fields['do_blast'].setChecked(False)
        self._fields['run_ipcress'].setChecked(False)
        #start pipeline thread
        self._pipeline_thread.start()
    #end def
    
    
    #for pipeline thread to call
    #lock analyse and reset buttons while analysis is running
    @pyqtSlot(bool)
    def lock_buttons(self, lock=True):
        self.analyseButton.setEnabled(not lock)
        self.resetButton.setEnabled(not lock)
        if lock: self.abortButton.show()
        else: self.abortButton.hide()
    #end def
    
    
    #show result tabs
    @pyqtSlot()
    def show_results(self):
        #display reports
        for report in self._reports:
            #load report
            report_widget = QPlainTextEdit()
            font = QFont()
            font.setFamily('Monospace')
            report_widget.setFont(font)
            report_widget.setReadOnly(True)
            try:
                report_file = open(report[1], 'r')
                report_text = report_file.read()
                report_file.close()
            except Exception, e:
                print 'Unable to load report file:', report[1]
                print_exception(e)
                continue
            report_widget.insertPlainText(QString.fromUtf8(report_text))
            report_widget.moveCursor(QTextCursor.Start, QTextCursor.MoveAnchor)
            self.mainTabs.addTab(report_widget, report[0])
        #alert main window
        QApplication.alert(self)
    #end def
        
        
    #stdout/err catcher
    def write(self, text):
        self._append_terminal_output.emit(QString.fromUtf8(text))
        
    def flush(self): pass
        
        
    #abort handler
    @pyqtSlot()
    def _abort_analysis(self):
        if self._pipeline_thread.isRunning():
            self._pipeline_thread_stop.emit()
    
    
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