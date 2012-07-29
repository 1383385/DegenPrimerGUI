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
from PyQt4 import uic
from PyQt4.QtCore import QObject, QThread, pyqtSlot, pyqtSignal
from PyQt4.QtGui import QMainWindow, QFormLayout, QGroupBox, QLineEdit, \
QDoubleSpinBox, QSpinBox, QCheckBox, QFileDialog, QPushButton, QPlainTextEdit, QFont
from DegenPrimer.DegenPrimerConfig import DegenPrimerConfig
from DegenPrimer.DegenPrimerPipeline import degen_primer_pipeline
from DegenPrimer.StringTools import wrap_text, print_exception


class DegenPrimerPipeline(QThread):
    '''Wrapper for degen_primer_pipeline with multi-threading'''
    lock_buttons = pyqtSignal(bool)
    show_results = pyqtSignal()
    
    def __init__(self, args):
        QThread.__init__(self)
        self._args = args
        self.lock_buttons.connect(self._args.lock_buttons)
        self.show_results.connect(self._args.show_results)
    #end def
    
    def run(self):
        self.lock_buttons.emit(True)
        degen_primer_pipeline(self._args)
        self.show_results.emit()
        self.lock_buttons.emit(False)
    #end def
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
            if text: text += ' '
            text += s
        self.parent().setText(self.trUtf8(text))
    #end def
    
    def text(self):
        text = unicode(self.parent().text())
        return text.split(' ')
    #end def
#end class


class DegenPrimerGUI(DegenPrimerConfig, QMainWindow):
    '''Graphical User Interface for degen_primer'''

    _ui_path = ('./', '/usr/local/share/degen_primer/', '/usr/share/degen_primer')
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
    _cwdir_option   = {'option':'save_reports_to',
                               'section'   :'config',
                               #number of arguments
                               'nargs'     :1,
                               #help string
                               'help'      :'Save reports to this directory.',
                               #type
                               'field_type':'directory', #for gui
                               #default value
                               'default'   :None}


    #stdout/err catcher signal
    _append_terminal_output = pyqtSignal(str)

    def __init__(self):
        #parent's constructors
        DegenPrimerConfig.__init__(self)
        QMainWindow.__init__(self)
        #setup configuration group
        self._groups[self._config_option['section']] = 'Configuration'
        #try to load UI
        for path in self._ui_path:
            try:
                uic.loadUi(path+self._ui_file, self)
                break
            except:
                print path+self._ui_file+' no such file.'
                pass
        if not self.centralwidget: 
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
        #setup terminal output
        self._append_terminal_output.connect(self.terminalOutput.insertPlainText)
        self.terminalOutput.textChanged.connect(self.terminalOutput.ensureCursorVisible)
        #pipeline thread
        self._pipeline_thread = DegenPrimerPipeline(self)
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
            label = option['option'].replace('_', ' ')+(' (%s)' % option['metavar'])
            field.setMinimum(float(option['limits'][0]))
            field.setMaximum(float(option['limits'][1]))
        elif option['field_type'] == 'integer':
            field = QSpinBox(self.centralWidget())
            label = option['option'].replace('_', ' ')+(' (%s)' % option['metavar'])
            field.setMinimum(int(option['limits'][0]))
            field.setMaximum(int(option['limits'][1]))
        elif option['field_type'] == 'boolean':
            field = QCheckBox(self.centralWidget())
            label = option['option'].replace('_', ' ')
        elif option['field_type'] == 'file' \
        or   option['field_type'] == 'directory':
            field = QLineEdit(self.centralWidget())
            label = QPushButton(option['option'].replace('_', ' '), self.centralWidget())
            file_dialog = QFileDialog(label, option['option'].replace('_', ' '))
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
        if field:
            #setup group box if necessary
            if option['section'] not in self._group_boxes:
                group_box = QGroupBox(self._groups[option['section']], self.centralWidget())
                self._group_boxes[option['section']] = QFormLayout(group_box)
                self.configForm.addWidget(group_box)
            #add a field to the layout
            field.setToolTip(wrap_text(option['help']))
            self._fields[option['option']] = field
            self._group_boxes[option['section']].addRow(label, field)
    #end def


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
        if config_file:
            DegenPrimerConfig.parse_configuration(self, unicode(config_file))
        else: DegenPrimerConfig.parse_configuration(self)
        #update form fields
        for option in self._options:
            #get value
            value = None
            exec_line = ('value = self.%(option)s\n')
            exec (exec_line % option)
            #update field
            if option['field_type'] == 'string' \
            or option['field_type'] == 'file':
                if not value: value = ''
                if option['nargs'] == 1:
                    self._fields[option['option']].setText(self.trUtf8(value))
                else:
                    self._fields[option['option']].findChild(LineEditWrapper).setText(value)
            elif option['field_type'] == 'float' \
            or   option['field_type'] == 'integer':
                if not value: value = 0
                self._fields[option['option']].setValue(value)
            elif option['field_type'] == 'boolean':
                if not value: value = False
                self._fields[option['option']].setChecked(value)
        self._fields_empty = False
    #end def
    
    
    @pyqtSlot('QString')
    def _load_config(self, config_file):
        self._fields_empty = True
        self.parse_configuration(config_file)
        if config_file and os.path.exists(os.path.dirname(unicode(config_file))):
            self._fields[self._cwdir_option['option']].setText(self.trUtf8(os.path.dirname(unicode(config_file))))
    #end def
    
    
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
        self.terminalOutput.clear()
        self._clear_results()
        self._config_file = unicode(self._fields[self._config_option['option']].text())
        cwdir_field = self._fields[self._cwdir_option['option']]
        cwdir = unicode(cwdir_field.text())
        while not os.path.isdir(cwdir):
            file_dialog = QFileDialog(None, 'Select a directory to save reports to...')
            file_dialog.setFileMode(QFileDialog.Directory)
            file_dialog.setOption(QFileDialog.ShowDirsOnly, True)
            file_dialog.setModal(True)
            file_dialog.fileSelected.connect(cwdir_field.setText)
            file_dialog.exec_()
            cwdir = unicode(cwdir_field.text())
        os.chdir(cwdir)
        print 'Current directory is %s\n' % os.getcwd()
        self.parse_configuration(self._config_file)
        self._pipeline_thread.start()
    #end def
    
    
    #for pipeline thread to call
    @pyqtSlot(bool)
    def lock_buttons(self, lock=True):
        self.analyseButton.setEnabled(not lock)
        self.resetButton.setEnabled(not lock)

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
            report_widget.insertPlainText(self.trUtf8(report_text))
            self.mainTabs.addTab(report_widget, report[0])
    #end def
        
        
    #stdout/err catcher
    def write(self, text):
        self._append_terminal_output.emit(self.trUtf8(text))
#end class


#tests
import sys
from PyQt4.QtGui import QApplication

if __name__ == '__main__':
    app = QApplication(sys.argv)
    main = DegenPrimerGUI()
    sys.stdout = main
    sys.stderr = main
    main.show()
    sys.exit(app.exec_())