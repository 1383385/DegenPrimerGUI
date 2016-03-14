# coding=utf-8
#
# Copyright (C) 2013 Allis Tauri <allista@gmail.com>
# 
# DegenPrimerGUI is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# DegenPrimerGUI is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.

'''
Created on Feb 5, 2016

@author: Allis Tauri <allista@gmail.com>
'''

import os, errno
 
from BioUtils.Tools.Output import OutIntercepter
from PyQt4.QtCore import QThread, pyqtSignal
from Queue import Queue

class QtOutput(OutIntercepter, Queue):
    
    class _Reader(QThread):
        message_received = pyqtSignal(str)
        
        def __init__(self, queue):
            QThread.__init__(self)
            self._queue = queue
            self._running = False
            
        def run(self):
            self._running = True
            while self._running:
                try: 
                    msg = self._queue.get()
                    if msg is not None:
                        self.message_received.emit(msg)
                except IOError, e:
                    if e.errno == errno.EPIPE:
                        self._running = False
                except: pass
                
        def __del__(self):
            self._running = False
            self.wait()
            
        def stop(self): self._running = False
    #end class
    
    def __init__(self, maxsize=0):
        OutIntercepter.__init__(self)
        Queue.__init__(self, maxsize)
        self._debug = bool(os.environ.get('DP_DEBUG', False))
        if self._debug: print 'Debugging'
        self._reader = None
        
    def write(self, text):
        if self._debug: 
            self._out.write(text)
            self._out.flush() 
        self.put_nowait(text)
    
    def __enter__(self):
        OutIntercepter.__enter__(self)
        self._reader = self._Reader(self)
        self._reader.start()
        return self._reader
    
    def __exit__(self, _type, _value, _traceback):
        self._reader.stop()
        self._reader = None
        return OutIntercepter.__exit__(self, _type, _value, _traceback)