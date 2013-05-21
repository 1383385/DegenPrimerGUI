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
Created on Mar 4, 2013

@author: Allis Tauri <allista@gmail.com>
'''

import sys
import errno
import socket
import subprocess
import multiprocessing.connection as mpc
from time import sleep, time
from datetime import timedelta
from PyQt4.QtCore import QThread, pyqtSlot, pyqtSignal, QString, QTimer
from DegenPrimer.StringTools import print_exception
import degen_primer_pipeline


class StreamReader(QThread):
    '''Non-blocking continuous reading from a file-like object'''
    send_line = pyqtSignal(str)
    
    def __init__(self, _stream):
        QThread.__init__(self)
        self._stream    = _stream
        self._terminate = False
    #end def
    
    def run(self):
        while self._stream and not self._terminate:
            msg = self._stream.readline().decode('UTF-8')
            if msg: self.send_line.emit(QString.fromUtf8(msg))
    #end def

    @pyqtSlot()
    def stop(self): self._terminate = True
#end class


class DegenPrimerPipelineThread(QThread):
    '''Wrapper for degen_primer_pipeline with multi-threading'''
    
    #signals for the main thread
    _lock_buttons    = pyqtSignal(bool)
    _show_results    = pyqtSignal()
    _reload_seq_db   = pyqtSignal()
    _register_report = pyqtSignal(str, str)
    _update_timer    = pyqtSignal(str)
    
    
    def __init__(self, args):
        QThread.__init__(self)
        self._args     = args
        self._options  = None
        self._port     = 10000
        self._pipeline_file = degen_primer_pipeline.__file__
        self._pipeline_proc = None
        self._terminate     = False
        self._readers       = []
        #timer
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.setSingleShot(False)
        self._time0 = time()
        #signals
        self._lock_buttons.connect(self._args.lock_buttons)
        self._show_results.connect(self._args.show_results)
        self._reload_seq_db.connect(self._args.reload_sequence_db)
        self._register_report.connect(self._args.register_report)
        self._timer.timeout.connect(self._update_timer_string)
        self._update_timer.connect(self._args.update_timer)
    #end def
    
    
    def __del__(self):
        self._stop_readers()
        self._terminate_pipeline()
    #end def
    
        
    @pyqtSlot()
    def _update_timer_string(self):
        time_string = str(timedelta(seconds=time()-self._time0))[:-7]
        self._update_timer.emit(time_string)
    #end def
    
        
    @pyqtSlot(str)
    def on_error(self, msg): self.stop()
    #end def
    
    
    def _stop_readers(self):
        for reader in self._readers: 
            reader.stop()
    #end def
    
    
    def _cleanup(self, e=None):
        if e is Exception:
            print_exception(e)
        self._stop_readers()
        self._timer.stop()
        self._lock_buttons.emit(False)
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
                print '\nError: DegenPrimer Pipeline subprocess could not be properly terminated.'
                print 'You should kill it manually. PID: %d' % self._pipeline_proc.pid
            self._pipeline_proc = None
    #end def
    
    
    def pick_options(self): self._options = self._args.options
    
    def run(self):
        self._lock_buttons.emit(True)
        self._time0     = time()
        self._terminate = False
        listener        = None
        connection      = None
        reports         = None
        self._update_timer_string()
        self._timer.start()
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
                self._cleanup(e)
                return
        #run pipeline subprocess
        try:
            self._pipeline_proc = subprocess.Popen((sys.executable, '-u', #unbuffered I/O
                                                    self._pipeline_file,
                                                    str(self._port)),
                                                    stdin=subprocess.PIPE,
                                                    stdout=subprocess.PIPE,
                                                    stderr=subprocess.PIPE)
        except OSError, e:
            print '\nFaild to execute DegenPrimer Pipeline subprocess.'
            self._cleanup(e)
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
                self._cleanup(e)
                return
            except Exception, e:
                self._cleanup(e)
                return
        if self._terminate:
            self._cleanup()
            return
        #send pipeline options
        connection.send(self._options)
        #wait for the process to exit
        if self._pipeline_proc.wait() != 0:
            print ('DegenPrimer Pipeline subprocess exited with '
                   'exit code %d') % self._pipeline_proc.returncode
            self._cleanup()
            return
        else:
            #get results
            try: reports = connection.recv()
            except IOError: pass
            except EOFError: pass
            except Exception, e:
                self._cleanup(e)
                return
        #if reports were generated, register them
        if reports:
            for report in reports:
                self._register_report.emit(*report)
            self._show_results.emit()
        elif self._pipeline_proc.returncode == 0:
            self._reload_seq_db.emit()
        #close the listener and stop readers
        listener.close()
        self._cleanup()        
        return
    #end def
    
    
    @pyqtSlot()
    def stop(self):
        if not self._terminate:
            print '\nAbortintg...' 
            self._terminate = True
            self._terminate_pipeline()
#end class        