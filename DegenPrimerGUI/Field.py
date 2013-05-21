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
Created on Mar 26, 2013

@author: Allis Tauri <allista@gmail.com>
'''

import sys
from PyQt4.QtCore import QString, QSettings
from PyQt4.QtGui import QWidget, QGroupBox, QFrame, \
QLineEdit, QDoubleSpinBox, QSpinBox, QCheckBox, QFileDialog, QPushButton, \
QLabel, QGridLayout, QSizePolicy
from DegenPrimer.StringTools import wrap_text
from Widgets import PolyLineEdit, FileDialog


def trigger(func, *f_args, **f_kwargs):
    '''wrap particular function call into a trigger function'''
    def wrapped(*args, **kwargs):
        return func(*f_args, **f_kwargs)
    return wrapped
    

class Field(object):
    '''Recursive structure of gui-fields corresponding to Option objects'''
    
    customize_field = None    
        
    def __init__(self, option, parent):
        self._settings = QSettings()
        self.option    = option
        self.name      = option.name
        self.title     = self.name.replace('_', ' ')
        self.parent    = parent
        self.container = None
        self.field     = None
        if self.option.is_poly:
            new_parent = QFrame(self.parent)
            new_parent.setFrameShape(QFrame.StyledPanel)
            new_parent.setLayout(QGridLayout())
            self._addRow(new_parent, self.parent.layout())
            self.parent = new_parent
        self._build_field()
    #end def
    
    
    @staticmethod
    def _addRow(widget, layout):
        layout.addWidget(widget, layout.rowCount(), 0, 1, 2)
        
        
    @staticmethod
    def _del_field(field):
        if type(field) is list:
            for subfield in field:
                Field._del_field(subfield)
            while len(field): field.pop()
        elif type(field) is dict:
            for subfield in field.values():
                Field._del_field(subfield)
            field.clear()
        elif isinstance(field, Field):
            del field
        elif isinstance(field, QWidget):
            field.deleteLater()
    #end def
    
    def __del__(self):
        self._del_field(self.field)
        if self.option.is_compound:
            if self.option.is_poly:
                for cont in self.container: cont.deleteLater()
                self.parent.deleteLater()
            else: self.container.deleteLater()
    #end def
    
    
    def _add_or_set(self, var, val):
        if self.option.is_poly:
            if getattr(self, var) is None:
                setattr(self, var, [val,])
            else: getattr(self, var).append(val)
        else: setattr(self, var, val)
    #end def
    
    
    def _build_field(self):
        #build option
        if self.option.is_compound:
            #make container
            container = QGroupBox(self.title, self.parent)
            container.setToolTip(self.option.formatted_desc)
            layout    = QGridLayout(container)
            self._addRow(container, self.parent.layout())
            #make option
            if not self.option.is_poly or self.value_required or self.field is not None:
                field = dict((opt.name, Field(opt, container)) for opt in self.option.options)
                self._add_or_set('container', container)
                self._add_or_set('field', field)
            #add +/- buttons if poly-option
            if self.option.is_poly:
                new_row = layout.rowCount()
                if self.field is not None and len(self.field) > int(self.value_required):
                    del_button = QPushButton('-', container)
                    del_button.setToolTip('Delete this %s' % self.title)
                    del_option_gui = trigger(self._del_instance, self.field[-1], self.container[-1])
                    del_button.clicked.connect(del_option_gui)
                    layout.addWidget(del_button, new_row, 0)
                add_button = QPushButton('+', container)
                add_button.setToolTip('Add another %s' % self.title)
                add_button.clicked.connect(self._add_instance)
                layout.addWidget(add_button, new_row, 1)
        else: 
            field = self._make_simple_field(self.option, self.parent)
            self._add_or_set('field', field)
    #end def


    def _add_instance(self):
        if self.option.is_poly:
            if self.field is None: self.field = []
            self._build_field()
    #end def
    
    
    def _del_instance(self, field=None, container=None):
        if self.option.is_poly:
            if container:
                self.container.remove(container)
            else: container = self.container.pop()
            if field:
                self.field.remove(field)
            else: field = self.field.pop()
            self._del_field(field)
            container.deleteLater()
    #end def
    
    
    @classmethod
    def _make_simple_field(cls, option, parent):
        field  = None
        label  = option.name.replace('_', ' ')
        layout = parent.layout()
        if option.field_type == 'bool':
            field = QCheckBox(parent)
        elif option.field_type == 'str':
            if option.is_multi:
                field = PolyLineEdit(parent)
            else:
                field = QLineEdit(parent)
        elif option.field_type in ('float', 'int'):
            if option.field_type == 'float':
                field = QDoubleSpinBox(parent)
                field.setDecimals(option.decimals)
                field.setSingleStep(option.step)
            else:
                field = QSpinBox(parent)
            if option.units:
                label += (' (%s)' % option.units).replace('%%', '%')
            if option.limits:
                if option.limits[0] is not None:
                    field.setMinimum(float(option.limits[0]))
                if option.limits[1] is not None:
                    field.setMaximum(float(option.limits[1]))
                else: field.setMaximum(sys.maxint)
            if option.default:
                field.setValue(option.default)
        elif option.field_type in ('file', 'directory'):
            #label is a button which opens chooser dialog
            file_dialog = FileDialog(parent, label, option.name)
            label = QPushButton(label, parent)
            #button-label
            label.clicked.connect(file_dialog.show)
            #field itself
            if option.is_multi:
                field = PolyLineEdit(parent)
            else:
                field = QLineEdit(parent)
            #connect signals
            if option.field_type == 'file':
                if option.is_multi:
                    file_dialog.setFileMode(QFileDialog.ExistingFiles)
                    file_dialog.filesSelected.connect(field.setText)
                else:
                    file_dialog.fileSelected.connect(field.setText)
            else:
                file_dialog.setFileMode(QFileDialog.Directory)
                file_dialog.setOption(QFileDialog.ShowDirsOnly, True)
                file_dialog.fileSelected.connect(field.setText)
                field.textChanged.connect(file_dialog.setDirectory)
        if field:
            field.setToolTip(option.formatted_desc)
            if hasattr(cls.customize_field, '__call__'):
                cls.customize_field(option, field, label)
            if type(label) is str: 
                label = QLabel(label, parent)
                label.setToolTip(option.formatted_desc)
                label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
            row = layout.rowCount()
            layout.addWidget(label, row, 0)
            layout.addWidget(field, row, 1)
        return field 
    #end def
    
    
    @property
    def value_required(self): return self.option.value_required
    
    @property
    def value(self):
        value = None
        if type(self.field) is list:
            value = []
            for instance in self.field:
                if instance is None: continue
                inst_value = dict()
                for name, subfield in instance.items():
                    sub_value = subfield.value
                    if sub_value is None and subfield.value_required:
                        inst_value = None
                        break
                    inst_value[name] = sub_value
                if inst_value: value.append(inst_value)
        elif type(self.field) is dict:
            value = dict()
            for name, subfield in self.field.items():
                    sub_value = subfield.value
                    if sub_value is None and subfield.value_required:
                        value = None
                        break
                    value[name] = sub_value
        elif isinstance(self.field, QWidget):
            if isinstance(self.field, PolyLineEdit):
                value = self.field.text()
                if not value and self.value_required:
                    value = None
            elif isinstance(self.field, QLineEdit): 
                value = unicode(self.field.text())
                if not value and self.value_required:
                    value = None
            elif isinstance(self.field, QDoubleSpinBox) \
            or   isinstance(self.field, QSpinBox):
                value = self.field.value()
            elif isinstance(self.field, QCheckBox):
                value = self.field.isChecked()
        return value
    #end def
    
    
    @value.setter
    def value(self, value):
        if type(self.field) in (list, dict) \
        and type(self.field) != type(value):
            raise ValueError('Field.value: type of a value '
                             'should be the same as the type of the field.')
        if self.option.is_poly and self.field is None: self.field = []
        if type(self.field) is list:
            while len(self.field) < len(value):
                self._add_instance()
            while len(self.field) > len(value):
                self._del_instance()
            if not self.field and self.value_required: self._add_instance()
            else:
                for instance, inst_value in zip(self.field, value):
                    for name, subvalue in inst_value.items():
                        instance[name].value = subvalue
        elif type(self.field) is dict:
            for name, subvalue in value.items():
                self.field[name].value = subvalue
        elif isinstance(self.field, QWidget):
            if isinstance(self.field, PolyLineEdit):
                self.field.setText(value)
            elif isinstance(self.field, QLineEdit): 
                self.field.setText(QString.fromUtf8(value))
            elif isinstance(self.field, QDoubleSpinBox) \
            or   isinstance(self.field, QSpinBox):
                self.field.setValue(value)
            elif isinstance(self.field, QCheckBox):
                self.field.setChecked(value)
    #end def
#end class

