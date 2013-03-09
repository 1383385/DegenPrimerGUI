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
Created on Mar 4, 2013

@author: Allis Tauri <allista@gmail.com>
'''

import sys
import errno
import socket
import subprocess
import multiprocessing.connection as mpc
from time import sleep
from PyQt4.QtCore import QThread, pyqtSlot, pyqtSignal
from DegenPrimer.StringTools import print_exception
import degen_primer_pipeline


class StreamReader(QThread):
    '''Non-blocking continuous reading from a file-like object'''
    send_line = pyqtSignal(str)
    
    def __init__(self, _file):
        QThread.__init__(self)
        self._file      = _file
        self._terminate = False
    #end def
    
    def run(self):
        while self._file and not self._terminate:
            msg = self._file.readline()
            if msg: self.send_line.emit(msg)
            #sleep(0.1)
    #end def

    @pyqtSlot()
    def stop(self): self._terminate = True
#end class


class DegenPrimerPipelineThread(QThread):
    '''Wrapper for degen_primer_pipeline with multi-threading'''
    
    #signals for the main thread
    _lock_buttons    = pyqtSignal(bool)
    _show_results    = pyqtSignal()
    _register_report = pyqtSignal(str, str)
    
    
    def __init__(self, args):
        QThread.__init__(self)
        self._args     = args
        #self._pipeline = DegenPrimerPipeline()
        self._port     = 10000
        self._pipeline_file = degen_primer_pipeline.__file__
        self._pipeline_proc = None
        self._terminate     = False
        self._readers       = []
        self._lock_buttons.connect(self._args.lock_buttons)
        self._show_results.connect(self._args.show_results)
        self._register_report.connect(self._args.register_report)
    #end def
    
    
    def __del__(self):
        self._stop_readers()
        self._terminate_pipeline()
    #end def
    
        
    @pyqtSlot(str)
    def on_error(self, msg): self.stop()
    #end def
    
    
    def _stop_readers(self):
        for reader in self._readers: 
            reader.stop()
            #reader.wait()
    #end def
    
        
    def _terminate_pipeline(self):
        if not self._pipeline_proc: return
        if self._pipeline_proc.poll() is None:
            self._pipeline_proc.terminate()
            sleep(1)
            if self._pipeline_proc.poll() is None:
                self._pipeline_proc.kill()
                sleep(1)
            if self._pipeline_proc.poll() is None:
                print 'Error: DegenPrimer Pipeline subprocess could not be properly terminated.'
                print 'You should kill it manually. PID: %d' % self._pipeline_proc.pid
            self._pipeline_proc = None
    #end def
    
    
    def run(self):
        self._lock_buttons.emit(True)
        self._terminate = False
        listener        = None
        connection      = None
        reports         = None
        #open connection to listen to the pipeline subprocess
        while not self._terminate:
            try:
                listener = mpc.Listener(('localhost', self._port), authkey="degen_primer_auth")
                break
            except socket.error, e:
                if e.errno in (errno.EADDRINUSE,
                               errno.EACCES):
                    self._port += 1
                    continue
                print '\nException has occured while executing DegenPrimer Pipeline. Please, try again.'
                print e.errno, e.message
                self._lock_buttons.emit(False)
                return
        #run pipeline subprocess
        try:
            self._pipeline_proc = subprocess.Popen((sys.executable, '-u', #unbuffered I/O
                                                    self._pipeline_file,
                                                    self._args.config_file,
                                                    str(self._port)),
                                                    stdout=subprocess.PIPE,
                                                    stderr=subprocess.PIPE)
        except OSError, e:
            print '\nFaild to execute DegenPrimer Pipeline subprocess.'
            print_exception(e)
            self._lock_buttons.emit(False)
            return
        #setup stream readers
        self._readers.append(StreamReader(self._pipeline_proc.stderr))
        self._readers[-1].send_line.connect(self._args.write)
        self._readers[-1].send_line.connect(self.on_error)
        self._readers[-1].start()
        self._readers.append(StreamReader(self._pipeline_proc.stdout))
        self._readers[-1].send_line.connect(self._args.write)
        self._readers[-1].start()
        #accept the connection
        while not self._terminate:
            try:
                connection = listener.accept()
                break
            except IOError, e:
                if e.errno == errno.EINTR:
                    print_exception(e)
                    sleep(0.1)
                    continue
                print_exception(e)
                self._stop_readers()
                self._lock_buttons.emit(False)
                return
        #wait for the process to exit
        if self._pipeline_proc.wait() != 0:
            print ('DegenPrimer Pipeline subprocess exited with '
                   'exit code %d') % self._pipeline_proc.returncode
            self._stop_readers()
            self._lock_buttons.emit(False)
            return
        else:
            #get results
            try: reports = connection.recv()
            except IOError: pass
            except EOFError: pass
            except Exception, e:
                print_exception(e)
                self._stop_readers()
                self._lock_buttons.emit(False)
                return
        #if reports were generated, register them
        if reports:
            for report in reports:
                self._register_report.emit(*report)
            self._show_results.emit()
        #close the listener and stop readers
        listener.close()
        self._stop_readers()
        self._lock_buttons.emit(False)        

    #end def
    
    
    @pyqtSlot()
    def stop(self):
        if not self._terminate:
            print '\nAbortintg...' 
            self._terminate = True
            self._terminate_pipeline()
#end class        