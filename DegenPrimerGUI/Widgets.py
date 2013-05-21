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

from PyQt4.QtCore import Qt, QString, QSettings, pyqtSlot, pyqtSignal
from PyQt4.QtGui import QLineEdit, QTableWidget, QTableWidgetItem,  \
QAbstractItemView, QFileDialog

from DegenPrimer.SeqDB import SeqDB


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
    
    def __init__(self, parent):
        QTableWidget.__init__(self, parent)
        self.setColumnCount(2)
        self.verticalHeader().hide()
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.MultiSelection)
        self.setSortingEnabled(True)
        self.cellClicked.connect(self._get_ids)
        self._seq_db = SeqDB()
    #end def
    
    def __del__(self):
        self._seq_db.close()
    #end def
    
    
    def clear(self):
        QTableWidget.clear(self)
        self.setRowCount(0)
        self.setHorizontalHeaderLabels(['ID', 'sequence name'])
    #end def
    
    
    @pyqtSlot('QString')
    def list_db(self, db_filename):
        self.clear()
        db_filename = unicode(db_filename)
        if not self._seq_db.connect(db_filename): return False
        seq_names = self._seq_db.get_names()
        self._seq_db.close()
        if not seq_names: return False
        for _id, name in seq_names.items():
            self.insertRow(0)
            self.setItem(0, 0, QTableWidgetItem(str(_id)))
            self.setItem(0, 1, QTableWidgetItem(str(name)))
        self.setMinimumHeight(self.rowHeight(0)*min(11, len(seq_names)))
        self.sortByColumn(1, Qt.AscendingOrder)
        self.resizeColumnsToContents()
        return True
    #end def
    
    
    @pyqtSlot('int', 'int')
    def _get_ids(self, row, col):
        ids = self.get_ids()
        if ids: self.send_ids.emit(ids)
    #end def
    
    
    @pyqtSlot()
    def get_ids(self):
        selected = self.selectedItems()
        ids = []
        for item in selected:
            if item.column() != 0: continue
            ids.append(unicode(item.text()))
        return ids
    #end def
    
    
    @pyqtSlot('QString')
    def set_ids(self, ids):
        self.clearSelection()
        ids = unicode(ids).split(', ')
        if ids:
            for _id in ids:
                if not _id: continue
                items = self.findItems(_id.rstrip(', '), Qt.MatchExactly)
                selected = self.selectedItems()
                for item in items:
                    if item not in selected:
                        self.selectRow(item.row())
    #end def
#end class