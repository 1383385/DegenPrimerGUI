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
Created on Mar 23, 2013

@author: Allis Tauri <allista@gmail.com>
'''

from __future__ import print_function

from PyQt4.QtCore import Qt, QString, QSettings, pyqtSlot, pyqtSignal
from PyQt4.QtGui import QLineEdit, QTableWidget, QTableWidgetItem,  \
QAbstractItemView, QFileDialog

from .SubprocessThread import SubprocessThread
from . import seq_loader

class PolyLineEdit(QLineEdit):
    '''Wrapper for QLineEdit which overloads setText 
    to make it accept list of strings'''
    def __init__(self, parent):
        QLineEdit.__init__(self, parent)
    
    @pyqtSlot('QStringList')
    def setText(self, strings):
        text = u', '.join([unicode(string) for string in strings])
        QLineEdit.setText(self, QString.fromUtf8(text))
    #end def
    
    def text(self):
        text = unicode(QLineEdit.text(self))
        return [item.rstrip(', ') for item in text.split(', ') if item]
    #end def
#end class


class FileDialog(QFileDialog):
    def __init__(self, parent, title, name):
        QFileDialog.__init__(self, parent, title)
        self._name     = name
        self._settings = QSettings()
        self._restore_state()
        self.currentChanged.connect(self._save_state)
    #end def
    
    def _save_state(self):
        self._settings.setValue(self._name+'/dialog_state', 
                                self.saveState())
        self._settings.setValue(self._name+'/size', 
                                self.size())
        self._settings.setValue(self._name+'/directory', 
                                self.directory().absolutePath())
        self._settings.setValue('sidebar_urls', self.sidebarUrls())
    #end def

    def _restore_state(self):
        dialog_state = self._settings.value(self._name+'/dialog_state', defaultValue=None)
        if dialog_state != None:
            self.restoreState(dialog_state.toByteArray())
        dialog_size  = self._settings.value(self._name+'/size', defaultValue=None)
        if dialog_size != None:
            self.resize(dialog_size.toSize())
        dialog_dir   = self._settings.value(self._name+'/directory', defaultValue=None)
        if dialog_dir != None:
            self.setDirectory(dialog_dir.toString())
        sidebar_urls = self._settings.value('sidebar_urls', defaultValue=None)
        if sidebar_urls != None:
            urls = [url.toUrl() for url in sidebar_urls.toList()]
            self.setSidebarUrls(urls)
    #end def
#end class


class SequenceTableWidget(QTableWidget):
    '''TableWidget that lists content of sequence database and returns IDs of
    selected sequences'''
    
    send_ids = pyqtSignal(list)
    abort_loading = pyqtSignal()
    loaded = pyqtSignal()
    
    def __init__(self, parent=None):
        QTableWidget.__init__(self, parent)
        self.hide()
        self.setColumnCount(2)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.MultiSelection)
#        self.setSortingEnabled(True)
        self.cellClicked.connect(self._get_ids)
        self._loader = None
    
    def __del__(self):
        if self._loader is not None:
            self._loader.stop()
        
    def clear(self):
        QTableWidget.clear(self)
        self.setRowCount(0)
        self.setHorizontalHeaderLabels(['ID', 'description'])
    
    @staticmethod
    def _readonly(_it):
        _it.setFlags(_it.flags() ^ Qt.ItemIsEditable)
        return _it
    
    @pyqtSlot(list)
    def _add_row(self, (sid, description)):
        self.insertRow(0)
        self.setItem(0, 0, self._readonly(QTableWidgetItem(sid)))
        self.setItem(0, 1, self._readonly(QTableWidgetItem(description)))
        
    @pyqtSlot(bool)
    def _db_loaded(self, _success):
        self.setMinimumHeight(self.rowHeight(0)*min(11, self.rowCount()))
        self.resizeColumnsToContents()
        self.loaded.emit()
        self._loader = None
        self.show()
        
    def load_db(self, filenames):
        self.clear()
        self._loader = SubprocessThread(seq_loader)
        self._loader.results_received.connect(self._add_row)
        self._loader.finished.connect(self._db_loaded)
        self._loader.message_received.connect(print)
        self.abort_loading.connect(self._loader.stop)
        self._loader.set_data(filenames)
        self._loader.start()
        
    @property
    def loading(self): return self._loader is not None
    
    @pyqtSlot('int', 'int')
    def _get_ids(self, row, col):
        ids = self.get_ids()
        if ids: self.send_ids.emit(ids)
    
    @pyqtSlot()
    def get_ids(self):
        selected = self.selectedItems()
        ids = []
        for item in selected:
            if item.column() != 0: continue
            ids.append(unicode(item.text()))
        return ids
    
    @pyqtSlot('QString')
    def set_ids(self, ids):
        self.clearSelection()
        ids = unicode(ids).split(', ')
        if not ids: return
        for sid in ids:
            if not sid: continue
            items = self.findItems(sid.rstrip(', '), Qt.MatchExactly)
            for item in items:
                selected = self.selectedItems()
                if item not in selected:
                    self.selectRow(item.row())
#end class