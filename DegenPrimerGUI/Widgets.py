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

from PyQt4.QtCore import Qt, QString, QSettings, pyqtSlot, pyqtSignal, QThread, \
QAbstractTableModel, QModelIndex, QVariant
from PyQt4.QtGui import QLineEdit, QTableWidget, QTableWidgetItem,  \
QAbstractItemView, QFileDialog, QTableView

from BioUtils.SeqUtils import SeqView, pretty_rec_name

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
        return [it for it in (item.strip() for item in text.split(',')) if it]
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

#adapted from https://sateeshkumarb.wordpress.com/2012/04/01/paginated-display-of-table-data-in-pyqt/
class SequenceTableModel(QAbstractTableModel):
    
    rows_to_load = 10
    
    select_row = pyqtSignal(int)
    
    def __init__(self, db, parent=None):
        super(SequenceTableModel, self).__init__(parent)
        self._header = ['ID', 'description']
        self._db     = db
        self._rows   = []
        self._to_select = []
        self.fetchMore()
    
    def rowCount(self, index=QModelIndex()):
        dbl = len(self._db); nrows = len(self._rows)
        return dbl if dbl < nrows else nrows
    
    def canFetchMore(self, index=QModelIndex()):
        return len(self._db) > len(self._rows)
 
    def fetchMore(self, index=QModelIndex()):
        start = len(self._rows)
        end = start+min(len(self._db) - start, self.rows_to_load)
        self.beginInsertRows(QModelIndex(), start, end-1)
        self._rows.extend((sid, pretty_rec_name(self._db[sid])) for sid in self._db.keys()[start:end])
        self.endInsertRows()
        if self._to_select and start <= self._to_select[0]:
            selected = 0
            for row in self._to_select:
                if row >= end: break
                self.select_row.emit(row)
                selected += 1
            self._to_select = self._to_select[selected:]                
 
    def columnCount(self,index=QModelIndex()):
        return len(self._header)
 
    def data(self, index, role=Qt.DisplayRole):
        if role != Qt.DisplayRole: return QVariant() #why?
        col = index.column()
        row = self._rows[index.row()]
        return QVariant(row[col]) if col < len(row) else QVariant()
    
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole: return QVariant()
        if orientation == Qt.Horizontal:
            return QVariant(self._header[section])
        return QVariant(int(section + 1))
    
    def sid(self, index): return self._db.keys()[index]
    
    def sindex(self, sid): 
        try: return self._db.keys().index(sid)
        except ValueError: return -1
        
    def sindexes(self, sids):
        found = []
        for i, k in enumerate(self._db.keys()):
            if len(found) >= len(sids): break
            if k in sids: found.append(i)
        return found
    
    def to_select(self, rows):
        self._to_select = rows


class SequenceTableView(QTableView):
    '''TableWidget that lists content of sequence database and returns IDs of
    selected sequences'''
    
    send_ids = pyqtSignal(list)
    abort_loading = pyqtSignal()
    loaded = pyqtSignal()
    
    class _Loader(QThread):
        loaded = pyqtSignal()
        def __init__(self, filenames):
            QThread.__init__(self)
            self.db = None
            self.filenames = filenames
            
        def __del__(self):
            self.wait()
            
        def run(self):
            self.db = SeqView()
            self.db.load(self.filenames)
            self.loaded.emit()
            
    def __init__(self, parent=None):
        QTableView.__init__(self, parent)
        self.hide()
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.MultiSelection)
        self.setHorizontalScrollMode(self.ScrollPerPixel)
        self.setAlternatingRowColors(True)
        self.setWordWrap(True)
        self.clicked.connect(self._toggle_selection)
        self._loader = None
        self._db = None
        self._selected = []
    
    def __del__(self):
        if self._loader is not None:
            self._loader.wait()
        if self._db is not None: 
            self._db.close()
        
    def clear(self):
        self.clearSelection()
        self.setModel(None)
        if self._db is not None: 
            self._db.close()
        self._db = None
    
    @pyqtSlot()
    def _db_loaded(self):
        self._db = self._loader.db.clone()
        self._loader.db.close()
        self._loader = None
        if self._db: 
            self.setModel(SequenceTableModel(self._db))
            self.setMinimumHeight(self.rowHeight(0)*min(SequenceTableModel.rows_to_load+1, len(self._db)))
            self.resizeColumnsToContents()
            self.model().select_row.connect(self.selectRow)
            self.show()
        else: self.clear()
        self.loaded.emit()
        
    def load_db(self, filenames):
        self.clear()
        self._loader = self._Loader(filenames)
        self._loader.loaded.connect(self._db_loaded)
        self.abort_loading.connect(self._loader.terminate)
        self._loader.start()
        
    @property
    def loading(self): return self._loader is not None
    
    @pyqtSlot('QModelIndex')
    def _toggle_selection(self, index):
        try: 
            i = self._selected.index(index.row())
            del self._selected[i]
        except ValueError:
            self._selected.append(index.row())
        self.send_ids.emit([self.model().sid(row) for row in self._selected])
        
    def clearSelection(self):
        self._selected = []
        QTableView.clearSelection(self)
    
    @pyqtSlot('QString')
    def set_ids(self, ids):
        self.clearSelection()
        ids = [sid.rstrip(', ') for sid in unicode(ids).split(', ')]
        if not ids: return
        model = self.model()
        rows_loaded = model.rowCount()
        self._selected = model.sindexes(ids)
        for i, row in enumerate(self._selected):
            if row >= rows_loaded:
                model.to_select(self._selected[i:])
                break
            self.selectRow(row)
                
    def scrollTo(self, index, hint = QTableView.EnsureVisible):
        if hint != QTableView.EnsureVisible:
            QTableView.scrollTo(self, index, hint)
#end class