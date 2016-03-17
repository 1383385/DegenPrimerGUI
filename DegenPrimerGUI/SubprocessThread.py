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
Created on Nov 10, 2013

@author: Allis Tauri <allista@gmail.com>
'''

import os
import sys
import errno
import socket
import subprocess
import binascii
import multiprocessing.connection as mpc
from time import sleep, time
from datetime import timedelta
from PyQt4.QtCore import QThread, pyqtSlot, pyqtSignal, QString, QTimer


class StreamReader(QThread):
    '''Non-blocking continuous reading from a file-like object'''
    message_received = pyqtSignal(str)
    
    def __init__(self, _stream):
        QThread.__init__(self)
        self._stream = _stream
        self._abort  = False
    #end def
    
    def _read_and_send(self):
        if not self._stream: return False
        msg = self._stream.readline().decode('UTF-8')
        if not msg: return False
        self.message_received.emit(QString.fromUtf8(msg))
        return True
    #end def
    
    def run(self):
        #read messages and send them as QStrings
        while not self._abort: self._read_and_send()
        #send last messages
        while self._read_and_send(): pass
    #end def

    @pyqtSlot()
    def stop(self): self._abort = True
#end class


class SubprocessThread(QThread):
    '''Wrapper for subprocess with multi-threading'''
    
    #signals for the main thread
    started          = pyqtSignal()
    finished         = pyqtSignal(bool)
    update_timer     = pyqtSignal(str)
    results_received = pyqtSignal(object)
    message_received = pyqtSignal(str)
    
    
    def __init__(self, module):
        QThread.__init__(self)
        self._data       = None
        self._executable = module.__file__
        self._subprocess = None
        self._abort      = False
        self._auth       = None
        self._port       = 10000
        self._readers    = []
        self._listener   = None
        self._connection = None
        #timer
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.setSingleShot(False)
        self._time0 = time()
        self._timer.timeout.connect(self._update_timer_string)
    #end def
        
    def __del__(self): 
        self._cleanup()
        self.wait()
    
    @pyqtSlot()
    def _update_timer_string(self):
        time_string = str(timedelta(seconds=time()-self._time0))[:-7]
        self.update_timer.emit(time_string)
    #end def
    
    @pyqtSlot(str)
    def _on_error(self, msg): self.stop()
    
    def _stop_readers(self):
        for reader in self._readers: 
            reader.stop()
            reader.wait()
        self._readers = []
    #end def
    
    def _abort_subprocess(self):
        if self._abort or self._connection is None: return
        try: self._connection.send('ABORT')
        except IOError: pass 
        self._abort = True
    #end def
    
    def _cleanup(self, e=None):
        if isinstance(e, Exception): print str(e)
        if self._listener is not None:
            self._listener.close()
            self._listener = None
        if self._subprocess is not None:
            self._abort_subprocess()
            self._subprocess.wait()
            self._subprocess = None
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        self._stop_readers()
        self._timer.stop() 
        self._auth = None
        self.finished.emit(e is None)
    #end def
    
    def _setup_listener(self):
        self._auth = binascii.b2a_hex(os.urandom(32))
        while not self._abort:
            try:
                self._listener = mpc.Listener(('localhost', self._port), 
                                              authkey=self._auth)
                return True
            except socket.error, e:
                if e.errno in (errno.EADDRINUSE,
                               errno.EACCES):
                    self._port += 1
                    continue
                print '\nException has occurred while executing %s. Please, try again.' % self._executable
                self._cleanup(e)
                return False
    #end def
    
    def _listen(self):
        while not self._abort:
            try: 
                self._connection = self._listener.accept()
                return True
            except IOError, e:
                if e.errno == errno.EINTR:
                    print str(e)
                    sleep(0.1)
                    continue
                self._cleanup(e)
                return False
            except Exception, e:
                self._cleanup(e)
                return False
        self._cleanup()
        return False
    #end def
    
    def _run_subprocess(self):
        try: 
            self._subprocess = subprocess.Popen((sys.executable, '-u', #unbuffered I/O
                                                 self._executable,
                                                 str(self._port)),
                                                stdin=subprocess.PIPE,
                                                stdout=subprocess.PIPE,
                                                stderr=subprocess.PIPE)
            self._subprocess.stdin.write(self._auth+'\n')
        except Exception, e:
            print '\nFaild to execute %s.' % self._executable
            self._cleanup(e)
            return False
        return self._subprocess is not None
    #end def
    
    def _receive_results(self):
        while not self._abort:
            try:
                results = self._connection.recv()
                if results is None: #exchange closing signals
                    self._connection.send(None)
                    return True 
                self.results_received.emit(results)
            except IOError: pass
            except EOFError: pass
            except Exception, e:
                self._cleanup(e)
                return False
        self._cleanup()
        return False
    #end def
    
    def set_data(self, data): self._data = data
    
    def run(self):
        self.started.emit()
        self._time0     = time()
        self._abort = False
        self._update_timer_string()
        self._timer.start()
        #open connection to listen to the subprocess
        if not self._setup_listener(): return
        #run subprocess
        if not self._run_subprocess(): return
        #setup stream readers
        self._readers.append(StreamReader(self._subprocess.stderr))
        self._readers[-1].message_received.connect(self.message_received)
#        self._readers[-1].message_received.connect(self._on_error)
        self._readers[-1].start()
        self._readers.append(StreamReader(self._subprocess.stdout))
        self._readers[-1].message_received.connect(self.message_received)
        self._readers[-1].start()
        #accept connection
        if not self._listen(): return
        #send data to the subprocess
        self._connection.send(self._data)
        #receive results
        if not self._receive_results(): return
        #wait for the process to exit
        if self._subprocess and self._subprocess.wait() != 0:
            print ('\nSubprocess\n   %s\n   exited with exit code %d\n' %
                   (self._executable, self._subprocess.returncode))
            self._cleanup(1)
            return
        #close the listener and stop readers
        self._cleanup()        
        return
    #end def
    
    @pyqtSlot()
    def stop(self):
        if not self._abort: print '\nAbortintg...\n'
        self._abort_subprocess() 
    #end def
#end class